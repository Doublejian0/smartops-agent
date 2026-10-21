"""
V1-2 路由Agent三层: 规则引擎 + RAG投票 + LLM兜底
对应架构图3.2: 漏斗判定(规则60% -> RAG投票20% -> LLM兜底20%)

运行: HF_HUB_OFFLINE=1 smartops-agent/.venv/Scripts/python.exe notebooks/router_agent_demo.py
"""
import os, re, json
from collections import Counter
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from chromadb.utils import embedding_functions
import chromadb

load_dotenv()
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
llm = ChatAnthropic(api_key=os.getenv('ARK_API_KEY'), base_url=os.getenv('ARK_BASE_URL'),
                    model=os.getenv('ARK_MODEL'), max_tokens=1024)
def get_text(r):
    c = r.content
    return c if isinstance(c, str) else ''.join(b.get('text', '') for b in c if b.get('type') == 'text')

DEPTS = ["控制器部门", "逆变器硬件组", "储能部门", "通信硬件组", "电网协议组", "充电桩组", "不确定"]

# === 建案例库(带 dept 元数据, 用于RAG投票)===
print("建案例库...")
bge_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name='BAAI/bge-large-zh', device='cuda')
client = chromadb.Client()
try: client.delete_collection("cases_v1")
except: pass
cases = client.create_collection("cases_v1", embedding_function=bge_ef)
case_docs = [
    ("光伏逆变器输出功率低于设定值,调度策略干预", "控制器部门"),
    ("功率限值触发,调度策略下发异常", "控制器部门"),
    ("光伏输出功率不符,dispatch_power限值", "控制器部门"),
    ("储能电池SOC跳变,BMS通信正常", "储能部门"),
    ("储能充放电异常,SOC校准偏差", "储能部门"),
    ("Modbus通信超时,寄存器无返回", "通信硬件组"),
    ("IEC104协议不通,TCP2404端口异常", "电网协议组"),
    ("逆变器过温,IGBT温度超阈值", "逆变器硬件组"),
]
cases.add(documents=[d for d, _ in case_docs], metadatas=[{"dept": dept} for _, dept in case_docs],
          ids=[f"c{i}" for i in range(len(case_docs))])

# === 第一层: 规则引擎(关键词正则, 毫秒级)===
RULES = [
    (r"modbus.*(超时|timeout|无返回)", "通信硬件组", 0.90),
    (r"SOC.*(跳变|异常|偏差)", "储能部门", 0.85),
    (r"(功率|出力).*(限值|调度|不符)", "控制器部门", 0.90),
    (r"IEC.?104.*(不通|超时)", "电网协议组", 0.88),
    (r"逆变器.*(过温|IGBT)", "逆变器硬件组", 0.92),
]
def route_rule(query):
    for pattern, dept, conf in RULES:
        if re.search(pattern, query, re.IGNORECASE):
            return dept, conf, "rule"
    return None

# === 第二层: RAG投票(检索Top5相似案例, 统计归属, ≥3同部门判该部门)===
def route_rag_vote(query):
    res = cases.query(query_texts=[query], n_results=5)
    depts = [m['dept'] for m in res['metadatas'][0]]
    counter = Counter(depts)
    top_dept, count = counter.most_common(1)[0]
    print(f"    [RAG投票] Top5归属分布: {dict(counter)}")
    if count >= 3:    # ≥3个同部门
        return top_dept, round(count / 5 * 0.8, 2), "rag_vote"
    return None

# === 第三层: LLM兜底 ===
def route_llm(query):
    resp = llm.invoke(f'判断故障归属部门,只输出JSON: {{"dept":"部门","reason":"理由"}}\n部门列表: {DEPTS}\n故障: {query}')
    m = re.search(r'\{.*\}', get_text(resp), re.DOTALL)
    d = json.loads(m.group()) if m else {}
    return d.get("dept", "不确定"), 0.40, "llm"

# === 三层漏斗 ===
def route(query):
    print(f"\n路由: 「{query}」")
    r = route_rule(query)
    if r: print(f"  -> 第1层规则命中: {r[0]} (置信度{r[1]})"); return r
    r = route_rag_vote(query)
    if r: print(f"  -> 第2层RAG投票: {r[0]} (置信度{r[1]})"); return r
    r = route_llm(query)
    print(f"  -> 第3层LLM兜底: {r[0]} (置信度{r[1]})"); return r

# === 测试3个case, 走不同层 ===
print("\n=== Case1: 含Modbus超时(应走规则)===")
route("Modbus通信超时,寄存器无返回")

print("\n=== Case2: 光伏发电量不够(规则未命中, 走RAG投票)===")
route("光伏发电量不够,出力偏低")

print("\n=== Case3: 设备发出奇怪声音(规则+RAG都难, 走LLM兜底)===")
route("设备发出奇怪声音")
print("\n✅ 路由Agent三层: 规则->RAG投票->LLM兜底 漏斗")
