"""
阶段2 LangGraph Demo: 多Agent协同编排(学图机制)
用图把 解析 -> 路由 -> (置信度分支)工单/专家研判 串起来
模拟数据(不调真LLM/检索), 先学 State/Node/Edge/条件分支

运行: smartops-agent/.venv/Scripts/python.exe notebooks/langgraph_demo.py
"""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

# === 1. State: 全局状态, 各节点共享传递的数据 ===
class DiagState(TypedDict):
    query: str            # 用户问题
    parsed: dict          # 解析结果
    dept: str             # 路由归属部门
    confidence: float     # 路由置信度
    result: str           # 最终结果

# === 2. Node: 每个节点是一个函数, 接收 state, 返回要更新的字段 ===
def parse_node(state: DiagState):
    print(f"  [解析节点] 处理问题: {state['query']}")
    return {"parsed": {"domain": "功率调度", "device": "逆变器"}}   # 只返回要更新的字段

def route_node(state: DiagState):
    # 模拟路由判定(规则引擎: 含"功率"归控制器, 高置信度)
    if "功率" in state['query']:
        dept, conf = "控制器部门", 0.85
    else:
        dept, conf = "不确定", 0.40
    print(f"  [路由节点] 归属={dept}, 置信度={conf}")
    return {"dept": dept, "confidence": conf}

def ticket_node(state: DiagState):
    print(f"  [工单节点] 高置信度, 自动生成工单 -> {state['dept']}")
    return {"result": f"工单草稿(归属:{state['dept']})"}

def expert_node(state: DiagState):
    print(f"  [专家节点] 低置信度, 转人工研判 -> {state['dept']}")
    return {"result": f"专家研判建议(归属:{state['dept']})"}

# === 3. 条件分支: 根据置信度决定走工单还是专家 ===
def after_route(state: DiagState) -> str:
    if state['confidence'] >= 0.7:
        return "ticket"    # 高置信度 -> 工单生成
    else:
        return "expert"    # 低置信度 -> 专家研判

# === 4. 建图: 把节点和边连起来 ===
graph = StateGraph(DiagState)
graph.add_node("parse", parse_node)
graph.add_node("route", route_node)
graph.add_node("ticket", ticket_node)
graph.add_node("expert", expert_node)

graph.add_edge(START, "parse")                                    # 入口 -> 解析
graph.add_edge("parse", "route")                                  # 解析 -> 路由
graph.add_conditional_edges("route", after_route,                 # 路由 -> 条件分支
                            {"ticket": "ticket", "expert": "expert"})
graph.add_edge("ticket", END)                                     # 工单 -> 结束
graph.add_edge("expert", END)                                     # 专家 -> 结束

app = graph.compile()

# === 5. 跑两个 case, 看条件分支怎么分流 ===
print("=== Case1: '光伏功率不对'(含功率, 高置信度)===")
r1 = app.invoke({"query": "光伏功率不对"})
print(f"  => 最终结果: {r1['result']}\n")

print("=== Case2: '设备异常'(模糊, 低置信度)===")
r2 = app.invoke({"query": "设备异常"})
print(f"  => 最终结果: {r2['result']}")

print("\n✅ 这就是LangGraph: State流转 + Node处理 + 条件分支 = 架构图编排引擎")
