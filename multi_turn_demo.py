# multi_turn_demo.py
# 演示多轮追问会话：checkpointer + interrupt
# 第一轮问模糊 -> interrupt 反问 -> 用户补充 -> 第二轮继续诊断
import asyncio
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.rag.embedding import get_or_create_collection
from src.orchestration.graph import build_graph


def build_demo_kb():
    docs = [
        ("光伏逆变器输出功率低于设定值, dispatch_power()限值逻辑", "功率调度"),
        ("Modbus通信超时,寄存器无返回", "通信"),
        ("储能电池SOC跳变,BMS通信状态异常", "储能"),
    ]
    dom2dept = {"功率调度": "控制器部门", "通信": "通信硬件组", "储能": "储能部门"}
    return get_or_create_collection(
        "multi_turn_kb",
        [(d, {"id": f"d{i}", "domain": dom, "dept": dom2dept.get(dom, "不确定")})
         for i, (d, dom) in enumerate(docs)],
    )


async def main():
    app = build_graph(build_demo_kb(), checkpointer=MemorySaver())
    thread = {"configurable": {"thread_id": "会话-001"}}  # 同一 thread_id 共享状态

    # 第 1 轮：模糊提问 -> 触发 interrupt 反问
    init = {"query": "设备异常", "parsed": {}, "dept": "", "route_conf": 0,
            "retrieved": [], "search_score": 0, "confidence": 0, "result": ""}
    r1 = await app.ainvoke(init, config=thread)

    print("=== 第 1 轮：模糊提问 ===")
    print("中断问题:", r1.get("__interrupt__"))
    print()

    # 第 2 轮：用户补充 -> resume 继续诊断
    print("=== 第 2 轮：用户补充 '逆变器输出功率15kW实测10kW' ===")
    r2 = await app.ainvoke(Command(resume="逆变器输出功率15kW实测10kW"), config=thread)
    print("dept:", r2.get("dept"), "| confidence:", r2.get("confidence"))
    print("result:", str(r2.get("result", ""))[:200])
    print()

    # 验证：同一 thread_id 记住了上一轮
    print("=== 会话状态验证 ===")
    print("ask_round:", r2.get("ask_round"), "| query:", r2.get("query"))


if __name__ == "__main__":
    asyncio.run(main())
