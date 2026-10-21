"""
0.4 完整 RAG 链路 Demo: 多查询 -> 检索 -> 合并去重 -> LLM生成带来源答案
整合前面所有: BGE embedding + ChromaDB + 多查询生成 + LLM生成
= V0 单链路核心(输入 -> 检索 -> 生成)

运行: smartops-agent/.venv/Scripts/python.exe notebooks/full_rag_demo.py
"""
import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from chromadb.utils import embedding_functions
import chromadb

load_dotenv()
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

def get_text(resp):
    """从 LangChain 响应取文本(处理 glm-5.2 的 thinking)"""
    c = resp.content
    return c if isinstance(c, str) else ''.join(b.get('text', '') for b in c if b.get('type') == 'text')

# === 1. 建知识库(ChromaDB + BGE)===
print("加载 BGE + 建知识库...")
bge_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name='BAAI/bge-large-zh', device='cuda')
client = chromadb.Client()
try: client.delete_collection("knowledge_base")
except: pass
kb = client.create_collection("knowledge_base", embedding_function=bge_ef)
docs = [
    "光伏逆变器输出功率低于设定值时,检查调度策略是否干预,dispatch_power()函数限值逻辑可能异常。",
    "储能电池SOC跳变,检查BMS通信状态,可能是SOC校准偏差。",
    "Modbus通信超时,检查寄存器地址合法性、波特率配置、终端电阻。",
    "功率限值触发条件:电网调度指令、需量管理、限电保护都可能干预输出功率。",
    "电网电压骤降会触发逆变器保护停机,这属于电网侧问题,非控制器部门。",
]
kb.add(documents=docs, metadatas=[{"id": f"doc{i}"} for i in range(len(docs))],
       ids=[f"doc{i}" for i in range(len(docs))])

# === 2. LLM(ChatAnthropic)===
llm = ChatAnthropic(api_key=os.getenv('ARK_API_KEY'), base_url=os.getenv('ARK_BASE_URL'),
                    model=os.getenv('ARK_MODEL'), max_tokens=2048)
user_query = "功率不对"

# === 3. 多查询生成(LLM 扩写 3 变体)===
resp = llm.invoke(f"你是SmartHEMS(光伏+储能)运维检索助手。把用户问题扩写成3个检索查询(标准化/根因向/细节向),每行一个,不要编号:\n用户问题: {user_query}")
queries = [user_query] + [q.strip() for q in get_text(resp).strip().split('\n') if q.strip()][:3]
print(f"\n【① 多查询】({len(queries)}个):")
for q in queries: print(f"  - {q}")

# === 4. 每个变体检索 ChromaDB + 合并去重 ===
seen, retrieved = set(), []
for q in queries:
    res = kb.query(query_texts=[q], n_results=2)
    for i in range(len(res['documents'][0])):
        doc, did, dist = res['documents'][0][i], res['metadatas'][0][i]['id'], res['distances'][0][i]
        if did not in seen:
            seen.add(did); retrieved.append((doc, did, dist))
retrieved.sort(key=lambda x: x[2])  # 按距离(越小越像)排序
print(f"\n【②③ 检索+合并去重】({len(retrieved)}条):")
for doc, did, dist in retrieved: print(f"  [{dist:.3f}] [{did}] {doc}")

# === 5. LLM 基于检索结果生成带来源答案 ===
context = '\n'.join(f"[{did}] {doc}" for doc, did, _ in retrieved)
resp2 = llm.invoke(f"你是SmartHEMS运维助手。根据知识库片段回答用户问题,回答中引用来源[docX]。\n\n知识库片段:\n{context}\n\n用户问题: {user_query}\n\n回答:")
print("\n【④ LLM 生成答案(带来源)】")
print(get_text(resp2))
print("\n✅ 完整RAG链路: 多查询 -> 检索 -> 合并 -> LLM生成带来源 = V0单链路核心")
