"""
阶段2 进阶: 真Agent接进LangGraph图(= V0完整流程雏形)
parse(LLM解析) -> route(规则) -> [置信度分支] ticket(LLM工单)/expert(LLM建议)
检索RAG节点暂未接, 先看真Agent串起来跑通

运行: HF_HUB_OFFLINE=1 smartops-agent/.venv/Scripts/python.exe notebooks/real_agents_graph.py
"""
import os, re
from typing import TypedDict
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langchain_anthropic import ChatAnthropic

load_dotenv()
llm = ChatAnthropic(api_key=os.getenv('ARK_API_KEY'), base_url=os.getenv('ARK_BASE_URL'),
                    model=os.getenv('ARK_MODEL'), max_tokens=2048)

def get_text(resp):
    c = resp.content
    return c if isinstance(c, str) else ''.join(b.get('text', '') for b in c if b.get('type') == 'text')

class DiagState(TypedDict):
    query: str
    parsed: str
    dept: str
    confidence: float
    result: str

# Node1: 解析(LLM结构化, 输出故障字段JSON)
def parse_node(state: DiagState):
    resp = llm.invoke(f'你是SmartHEMS运维助手。解析故障,只输出JSON: {{"domain":"领域","device":"设备","phenomenon":"现象"}}\n问题: {state["query"]}')
    text = get_text(resp)
    m = re.search(r'\{.*\}', text, re.DOTALL)
    parsed = m.group() if m else text
    print(f"  [解析] {parsed}")
    return {"parsed": parsed}

# Node2: 路由(规则引擎, 基于解析结果判归属+置信度)
def route_node(state: DiagState):
    p = state["parsed"]
    if "功率" in p or "调度" in p:      dept, conf = "控制器部门", 0.85
    elif "储能" in p or "SOC" in p:     dept, conf = "储能部门", 0.82
    elif "通信" in p or "Modbus" in p:  dept, conf = "通信硬件组", 0.88
    else:                                dept, conf = "不确定", 0.40
    print(f"  [路由] {dept} (置信度{conf})")
    return {"dept": dept, "confidence": conf}

def after_route(state: DiagState) -> str:
    return "ticket" if state["confidence"] >= 0.7 else "expert"

# Node3a: 工单生成(LLM结构化工单)
def ticket_node(state: DiagState):
    resp = llm.invoke(f'你是SmartHEMS工单助手。根据故障生成工单,只输出JSON: {{"title":"标题","suggested_dept":"{state["dept"]}","analysis":"初步分析"}}\n故障: {state["query"]}\n解析: {state["parsed"]}')
    print(f"  [工单] 生成工单 -> {state['dept']}")
    return {"result": get_text(resp)}

# Node3b: 专家研判(LLM建议)
def expert_node(state: DiagState):
    resp = llm.invoke(f'你是SmartHEMS专家。故障归属不确定,给3条排查建议,简答。\n故障: {state["query"]}')
    print(f"  [专家] 生成研判建议")
    return {"result": get_text(resp)}

# 建图
g = StateGraph(DiagState)
g.add_node("parse", parse_node)
g.add_node("route", route_node)
g.add_node("ticket", ticket_node)
g.add_node("expert", expert_node)
g.add_edge(START, "parse")
g.add_edge("parse", "route")
g.add_conditional_edges("route", after_route, {"ticket": "ticket", "expert": "expert"})
g.add_edge("ticket", END)
g.add_edge("expert", END)
app = g.compile()

# 跑两个case
print("=== Case1: 功率问题(应走工单)===")
r1 = app.invoke({"query": "光伏输出功率15kW设定但实测10kW"})
print(f"  结果: {r1['result'][:400]}\n")

print("=== Case2: 模糊问题(应走专家)===")
r2 = app.invoke({"query": "设备报警了"})
print(f"  结果: {r2['result'][:400]}")
print("\n✅ 真 Agent 接进 LangGraph: parse->route->分支->ticket/expert, V0流程雏形")
