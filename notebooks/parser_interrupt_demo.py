"""
V1 追问真实人在回路: interrupt暂停等用户输入 + resume恢复
对比 parser_agent_demo 的"模拟用户", 这里用 LangGraph interrupt 真实暂停
架构图"人工确认+修正反馈"的底层机制

运行: HF_HUB_OFFLINE=1 smartops-agent/.venv/Scripts/python.exe notebooks/parser_interrupt_demo.py
"""
import os, re, json
from typing import TypedDict
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command
from langchain_anthropic import ChatAnthropic

load_dotenv()
llm = ChatAnthropic(api_key=os.getenv('ARK_API_KEY'), base_url=os.getenv('ARK_BASE_URL'),
                    model=os.getenv('ARK_MODEL'), max_tokens=1024)
def get_text(r):
    c = r.content
    return c if isinstance(c, str) else ''.join(b.get('text', '') for b in c if b.get('type') == 'text')

class ParseState(TypedDict):
    query: str; parsed: dict; round: int; complete: bool

MANDATORY = ["devices", "phenomenon", "firmware_version"]

def parse_node(state: ParseState):
    resp = llm.invoke(f'解析故障,只输出JSON: {{"devices":"设备","phenomenon":"现象","firmware_version":"固件版本或未知"}}\n问题: {state["query"]}')
    m = re.search(r'\{.*\}', get_text(resp), re.DOTALL)
    parsed = json.loads(m.group()) if m else {}
    print(f"  [解析 round{state['round']}] {parsed}")
    return {"parsed": parsed}

def check_node(state: ParseState):
    p = state["parsed"]
    missing = [f for f in MANDATORY if not p.get(f) or p.get(f) == "未知"]
    filled = len(MANDATORY) - len(missing)
    complete = filled >= 2
    print(f"  [校验] 已填{filled}/3, 齐全={complete}")
    return {"complete": complete}

def ask_node(state: ParseState):
    # ★ 真实人在回路: interrupt 暂停整张图, 等用户输入(不模拟!)
    user_input = interrupt("请补充设备型号和固件版本")
    print(f"  [追问] 用户真实回复: {user_input}")
    return {"query": state["query"] + " " + user_input, "round": state["round"] + 1}

def after_check(state: ParseState) -> str:
    if state["complete"]: return "done"
    elif state["round"] < 2: return "ask"
    else: return "done"

g = StateGraph(ParseState)
g.add_node("parse", parse_node); g.add_node("check", check_node); g.add_node("ask", ask_node)
g.add_edge(START, "parse"); g.add_edge("parse", "check")
g.add_conditional_edges("check", after_check, {"ask": "ask", "done": END})
g.add_edge("ask", "parse")
app = g.compile(checkpointer=MemorySaver())    # checkpointer: 支持暂停/恢复

config = {"configurable": {"thread_id": "user123"}}

print("=== 第1次 invoke: 跑到 ask 暂停(等用户输入)===")
r = app.invoke({"query": "出故障了", "parsed": {}, "round": 0, "complete": False}, config)
print("  (图已冻结在 interrupt, state 已持久化, 等用户输入)\n")

print("=== (真实系统: 前端展示追问, 用户输入)===")
user_reply = "设备SUN2000-300KTL, 固件版本V3.2.1"
print(f"  用户真实输入: {user_reply}\n")

print("=== 第2次 invoke: resume 带用户输入, 图恢复继续 ===")
r = app.invoke(Command(resume=user_reply), config)
print(f"\n最终解析: {r['parsed']}")
print(f"齐全: {r['complete']}")
print("\n✅ 真实人在回路: interrupt暂停 -> 用户真实输入 -> resume恢复(不模拟)")
