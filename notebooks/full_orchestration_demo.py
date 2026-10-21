"""
V1-5 LangGraph完整编排: 串成图 + 置信度分支
parse -> route -> search -> skill -> confidence -> [≥0.7工单/<0.7专家]
综合置信度 = 路由×0.6 + 检索×0.4 (架构图7)

运行: HF_HUB_OFFLINE=1 PYTHONUTF8=1 smartops-agent/.venv/Scripts/python.exe notebooks/full_orchestration_demo.py
"""
import os, re
from typing import TypedDict
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langchain_anthropic import ChatAnthropic

load_dotenv()
llm = ChatAnthropic(api_key=os.getenv('ARK_API_KEY'), base_url=os.getenv('ARK_BASE_URL'),
                    model=os.getenv('ARK_MODEL'), max_tokens=1024)
def get_text(r):
    c = r.content
    return c if isinstance(c, str) else ''.join(b.get('text', '') for b in c if b.get('type') == 'text')

class State(TypedDict):
    query: str
    dept: str
    route_conf: float
    search_score: float
    confidence: float
    result: str

def parse_node(state: State):
    print(f"  [解析] {state['query']}"); return {}

def route_node(state: State):
    q = state['query']
    if "功率" in q: dept, conf = "控制器部门", 0.85
    elif "通信" in q or "Modbus" in q: dept, conf = "通信硬件组", 0.88
    else: dept, conf = "不确定", 0.40
    print(f"  [路由] {dept} (置信度{conf})")
    return {"dept": dept, "route_conf": conf}

def search_node(state: State):
    score = 0.80 if state['route_conf'] > 0.7 else 0.30   # 简化:路由明确则检索匹配高
    print(f"  [检索] 匹配度{score}")
    return {"search_score": score}

def skill_node(state: State):
    print(f"  [Skill] 匹配排查Skill(简化)"); return {}

def confidence_node(state: State):
    # 综合置信度 = 路由×0.6 + 检索×0.4 (架构图7)
    conf = state['route_conf'] * 0.6 + state['search_score'] * 0.4
    print(f"  [置信度] 综合={conf:.2f} = 路由{state['route_conf']}×0.6 + 检索{state['search_score']}×0.4")
    return {"confidence": conf}

def after_conf(state: State) -> str:
    return "ticket" if state['confidence'] >= 0.7 else "expert"

def ticket_node(state: State):
    resp = llm.invoke(f'生成工单,只输出JSON:{{"title":"标题","dept":"{state["dept"]}","analysis":"分析"}}\n故障:{state["query"]}')
    print(f"  [工单] 高置信度({state['confidence']:.2f}), 自动生成工单")
    return {"result": get_text(resp)}

def expert_node(state: State):
    resp = llm.invoke(f'故障归属不确定,给2条排查建议,简答。故障:{state["query"]}')
    print(f"  [专家] 低置信度({state['confidence']:.2f}), 转人工研判")
    return {"result": get_text(resp)}

# === 建图 ===
g = StateGraph(State)
for name, fn in [("parse",parse_node),("route",route_node),("search",search_node),
                 ("skill",skill_node),("confidence",confidence_node),("ticket",ticket_node),("expert",expert_node)]:
    g.add_node(name, fn)
g.add_edge(START, "parse"); g.add_edge("parse", "route"); g.add_edge("route", "search")
g.add_edge("search", "skill"); g.add_edge("skill", "confidence")
g.add_conditional_edges("confidence", after_conf, {"ticket": "ticket", "expert": "expert"})
g.add_edge("ticket", END); g.add_edge("expert", END)
app = g.compile()

print("=== Case1: 功率问题(应走工单)===")
r = app.invoke({"query":"光伏功率15kW实测10kW","dept":"","route_conf":0,"search_score":0,"confidence":0,"result":""})
print(f"  结果: {r['result'][:250]}\n")

print("=== Case2: 模糊问题(应走专家)===")
r = app.invoke({"query":"设备异常","dept":"","route_conf":0,"search_score":0,"confidence":0,"result":""})
print(f"  结果: {r['result'][:250]}")
print("\n✅ V1完整编排: parse->route->search->skill->置信度分支->ticket/expert")
