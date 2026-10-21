"""
V1-1 解析Agent: 字段校验 + 2轮追问(LangGraph 循环)
对应架构图3.1: 解析 -> 校验 -> (不全)追问 -> 再解析(循环, 最多2轮)
新点: LangGraph 循环(条件边回到 parse 节点)

运行: HF_HUB_OFFLINE=1 smartops-agent/.venv/Scripts/python.exe notebooks/parser_agent_demo.py
"""
import os, re, json
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

class ParseState(TypedDict):
    query: str
    parsed: dict
    round: int
    complete: bool

MANDATORY = ["devices", "phenomenon", "firmware_version"]   # 必填, 3选2

def parse_node(state: ParseState):
    resp = llm.invoke(f'解析故障,只输出JSON: {{"devices":"设备","phenomenon":"现象","firmware_version":"固件版本,未知则填未知"}}\n问题: {state["query"]}')
    m = re.search(r'\{.*\}', get_text(resp), re.DOTALL)
    parsed = json.loads(m.group()) if m else {}
    print(f"  [解析 round{state['round']}] {parsed}")
    return {"parsed": parsed}

def check_node(state: ParseState):
    p = state["parsed"]
    missing = [f for f in MANDATORY if not p.get(f) or p.get(f) == "未知"]
    filled = len(MANDATORY) - len(missing)
    complete = filled >= 2     # 3选2
    print(f"  [校验] 已填{filled}/3, 齐全={complete}" + (f", 缺{missing}" if missing else ""))
    return {"complete": complete}

def ask_node(state: ParseState):
    # 追问(实际系统问用户; demo里LLM生成追问话术 + 模拟用户补充)
    p = state["parsed"]
    missing = [f for f in MANDATORY if not p.get(f) or p.get(f) == "未知"]
    resp = llm.invoke(f'故障信息不全,缺失{missing}。生成一句简短追问请用户补充。只输出追问话术:')
    print(f"  [追问 round{state['round']}] {get_text(resp)}")
    # 模拟用户补充(实际等用户输入, 这里假设用户补了固件版本)
    simulated = "固件版本V3.2.1"
    print(f"  [模拟用户回复] {simulated}")
    return {"query": state["query"] + " " + simulated, "round": state["round"] + 1}

def after_check(state: ParseState) -> str:
    if state["complete"]:
        return "done"          # 齐全 -> 结束
    elif state["round"] < 2:
        return "ask"           # 不全且<2轮 -> 追问
    else:
        return "done"          # 2轮仍不全 -> 结束(标记信息不全)

# 建图: parse -> check -> (ask -> parse 循环 / done)
g = StateGraph(ParseState)
g.add_node("parse", parse_node)
g.add_node("check", check_node)
g.add_node("ask", ask_node)
g.add_edge(START, "parse")
g.add_edge("parse", "check")
g.add_conditional_edges("check", after_check, {"ask": "ask", "done": END})
g.add_edge("ask", "parse")     # ← 关键: 追问后回到解析, 形成循环
app = g.compile()

print("=== Case: 信息严重不全(只说'出故障了'), 触发追问循环 ===")
r = app.invoke({"query": "出故障了", "parsed": {}, "round": 0, "complete": False})
print(f"\n最终解析: {r['parsed']}")
print(f"轮次: {r['round']}, 齐全: {r['complete']}")
print("\n✅ 解析Agent: 字段校验 + 追问循环(LangGraph循环实现)")
