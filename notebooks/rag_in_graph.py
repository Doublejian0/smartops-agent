"""
阶段2: 检索RAG接进LangGraph图
parse -> route -> search(检索知识库) -> [置信度分支] ticket(基于检索)/expert(基于检索)
关键: 工单/专家不再LLM空想, 而是基于检索到的知识库内容生成

运行: HF_HUB_OFFLINE=1 smartops-agent/.venv/Scripts/python.exe notebooks/rag_in_graph.py
"""
import os, re
from typing import TypedDict
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langchain_anthropic import ChatAnthropic
from chromadb.utils import embedding_functions
import chromadb

load_dotenv()
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

llm = ChatAnthropic(api_key=os.getenv('ARK_API_KEY'), base_url=os.getenv('ARK_BASE_URL'),
                    model=os.getenv('ARK_MODEL'), max_tokens=2048)

def get_text(resp):
    c = resp.content
    return c if isinstance(c, str) else ''.join(b.get('text', '') for b in c if b.get('type') == 'text')

# === 建知识库(ChromaDB + BGE)===
print("加载 BGE + 建知识库...")
bge_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name='BAAI/bge-large-zh', device='cuda')
client = chromadb.Client()
try: client.delete_collection("knowledge_base")
except: pass
kb = client.create_collection("knowledge_base", embedding_function=bge_ef)
docs = [
    "光伏逆变器输出功率低于设定值:检查调度策略dispatch_power()限值逻辑、MPPT追踪、组件遮挡积灰。",
    "储能电池SOC跳变:检查BMS通信状态、SOC校准偏差、充放电策略干预。",
    "Modbus通信超时:检查寄存器地址合法性、波特率配置、终端电阻、线缆连接。",
    "功率限值触发条件:电网调度指令、需量管理、限电保护都可能干预输出功率。",
    "电网电压骤降触发逆变器保护停机:属电网侧问题,非控制器部门。",
]
kb.add(documents=docs, metadatas=[{"id": f"doc{i}"} for i in range(len(docs))],
       ids=[f"doc{i}" for i in range(len(docs))])

# === State ===
class DiagState(TypedDict):
    query: str
    parsed: str
    dept: str
    confidence: float
    retrieved: str      # 检索到的知识库内容
    result: str

# === Nodes ===
def parse_node(state: DiagState):
    resp = llm.invoke(f'你是SmartHEMS运维助手。解析故障,只输出JSON: {{"domain":"领域","device":"设备","phenomenon":"现象"}}\n问题: {state["query"]}')
    text = get_text(resp)
    m = re.search(r'\{.*\}', text, re.DOTALL)
    parsed = m.group() if m else text
    print(f"  [解析] {parsed}")
    return {"parsed": parsed}

def route_node(state: DiagState):
    p = state["parsed"]
    if "功率" in p or "调度" in p:      dept, conf = "控制器部门", 0.85
    elif "储能" in p or "SOC" in p:     dept, conf = "储能部门", 0.82
    elif "通信" in p or "Modbus" in p:  dept, conf = "通信硬件组", 0.88
    else:                                dept, conf = "不确定", 0.40
    print(f"  [路由] {dept} (置信度{conf})")
    return {"dept": dept, "confidence": conf}

def search_node(state: DiagState):
    # 检索知识库(向量检索), 召回相关文档
    res = kb.query(query_texts=[state["query"]], n_results=3)
    retrieved = '\n'.join(f"[doc{i}] {d}" for i, d in enumerate(res['documents'][0]))
    print(f"  [检索] 召回 {len(res['documents'][0])} 条知识库片段")
    return {"retrieved": retrieved}

def after_route(state: DiagState) -> str:
    return "ticket" if state["confidence"] >= 0.7 else "expert"

def ticket_node(state: DiagState):
    # 基于检索结果生成工单(不空想)
    resp = llm.invoke(f'你是SmartHEMS工单助手。根据知识库片段生成工单,只输出JSON: {{"title":"标题","suggested_dept":"{state["dept"]}","analysis":"初步分析(引用检索内容)"}}\n知识库:\n{state["retrieved"]}\n故障: {state["query"]}')
    print(f"  [工单] 基于检索生成工单 -> {state['dept']}")
    return {"result": get_text(resp)}

def expert_node(state: DiagState):
    # 基于检索结果给排查建议
    resp = llm.invoke(f'你是SmartHEMS专家。故障归属不确定,根据知识库片段给3条排查建议,简答。\n知识库:\n{state["retrieved"]}\n故障: {state["query"]}')
    print(f"  [专家] 基于检索生成建议")
    return {"result": get_text(resp)}

# === 建图: parse -> route -> search -> 分支 -> ticket/expert ===
g = StateGraph(DiagState)
g.add_node("parse", parse_node)
g.add_node("route", route_node)
g.add_node("search", search_node)
g.add_node("ticket", ticket_node)
g.add_node("expert", expert_node)
g.add_edge(START, "parse")
g.add_edge("parse", "route")
g.add_edge("route", "search")                                          # 路由后检索
g.add_conditional_edges("search", after_route, {"ticket": "ticket", "expert": "expert"})  # 检索后分支
g.add_edge("ticket", END)
g.add_edge("expert", END)
app = g.compile()

# === 跑 ===
print("\n=== Case1: 功率问题(走工单, 基于检索)===")
r1 = app.invoke({"query": "光伏输出功率15kW设定但实测10kW"})
print(f"  结果: {r1['result'][:500]}\n")

print("=== Case2: 模糊问题(走专家, 基于检索)===")
r2 = app.invoke({"query": "设备通信异常"})
print(f"  结果: {r2['result'][:500]}")
print("\n✅ RAG接进图: parse->route->search->分支->ticket/expert, 工单/专家基于检索结果")
