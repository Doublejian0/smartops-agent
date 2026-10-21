"""
V1-3 RAG升级: 多查询 + 元数据过滤(按路由domain) + BM25/向量混合 + RRF融合
整合0.3/0.4模块; 新点: 向量检索时 where=路由判的domain(架构图4.2前置过滤)
省略重排(0.3已学), 聚焦整合+元数据过滤

运行: HF_HUB_OFFLINE=1 smartops-agent/.venv/Scripts/python.exe notebooks/rag_pipeline_demo.py
"""
import os, re
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from chromadb.utils import embedding_functions
import chromadb, jieba, numpy as np
from rank_bm25 import BM25Okapi

load_dotenv()
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
llm = ChatAnthropic(api_key=os.getenv('ARK_API_KEY'), base_url=os.getenv('ARK_BASE_URL'),
                    model=os.getenv('ARK_MODEL'), max_tokens=1024)
def get_text(r):
    c = r.content
    return c if isinstance(c, str) else ''.join(b.get('text', '') for b in c if b.get('type') == 'text')

# === 建库(带 domain 元数据)===
print("建知识库(带domain)...")
bge_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name='BAAI/bge-large-zh', device='cuda')
client = chromadb.Client()
try: client.delete_collection("kb_v1")
except: pass
kb = client.create_collection("kb_v1", embedding_function=bge_ef)
docs = [
    ("光伏逆变器输出功率低于设定值,dispatch_power()限值逻辑", "功率调度"),
    ("功率限值触发:电网调度指令、需量管理、限电保护", "功率调度"),
    ("光伏输出功率不符,MPPT追踪异常", "功率调度"),
    ("储能电池SOC跳变,BMS通信状态检查", "储能"),
    ("储能充放电异常,SOC校准偏差", "储能"),
    ("Modbus通信超时,寄存器地址、波特率、终端电阻", "通信"),
    ("IEC104协议不通,TCP2404端口", "通信"),
    ("逆变器过温,IGBT温度超阈值", "逆变器"),
]
kb.add(documents=[d for d, _ in docs],
       metadatas=[{"id": f"doc{i}", "domain": dom} for i, (_, dom) in enumerate(docs)],
       ids=[f"doc{i}" for i in range(len(docs))])

# === 路由判 domain(简化规则)===
def get_domain(query):
    if "功率" in query or "出力" in query: return "功率调度"
    if "储能" in query or "SOC" in query: return "储能"
    if "Modbus" in query or "通信" in query: return "通信"
    if "逆变" in query and "温" in query: return "逆变器"
    return None   # 不确定 -> 不过滤

def rrf(ranks, k=60):
    s = {}
    for rank in ranks:
        for pos, did in enumerate(rank):
            s[did] = s.get(did, 0) + 1 / (k + pos)
    return sorted(s, key=s.get, reverse=True), s

# === 完整检索管线 ===
def retrieve(query):
    domain = get_domain(query)
    where = {"domain": domain} if domain else None
    print(f"  路由domain={domain}, where过滤={where}")
    # ① 多查询生成
    resp = llm.invoke(f"SmartHEMS运维。扩写成3个检索查询,每行一个,不要编号:\n{query}")
    queries = [query] + [q.strip() for q in get_text(resp).split('\n') if q.strip()][:3]
    print(f"  ①多查询({len(queries)}个)")
    # ② 每个变体: 向量召回(where过滤) + BM25召回
    all_docs = [d for d, _ in docs]
    bm25 = BM25Okapi([list(jieba.cut(d)) for d in all_docs])
    vec_ranks, bm25_ranks = [], []
    for q in queries:
        res = kb.query(query_texts=[q], n_results=5, where=where) if where else kb.query(query_texts=[q], n_results=5)
        vec_ranks.append([m['id'] for m in res['metadatas'][0]])
        scores = bm25.get_scores(list(jieba.cut(q)))
        bm25_ranks.append([f"doc{i}" for i in np.argsort(scores)[::-1][:5]])
    print(f"  ②两路召回(向量where过滤 + BM25)")
    # ③ RRF融合(多查询×两路)
    fused, scores = rrf(vec_ranks + bm25_ranks)
    print(f"  ③RRF融合")
    return fused[:5], scores

# === 测试 ===
print("\n=== Case1: 功率问题(domain=功率调度, 只搜功率文档)===")
top, sc = retrieve("光伏输出功率15kW实测10kW")
print("  Top5:", [(d, round(sc[d], 4)) for d in top])

print("\n=== Case2: 通信问题(domain=通信, 只搜通信文档)===")
top, sc = retrieve("Modbus通信超时")
print("  Top5:", [(d, round(sc[d], 4)) for d in top])
print("\n✅ RAG升级: 多查询+元数据过滤(按domain)+BM25/向量混合+RRF")
