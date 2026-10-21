# graph_state_monitor.py
# Graph 全链路状态监控（只看关键字段）
import asyncio
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
        "dbg_kb",
        [(d, {"id": f"d{i}", "domain": dom, "dept": dom2dept.get(dom, "不确定")})
         for i, (d, dom) in enumerate(docs)],
    )


def main():
    app = build_graph(build_demo_kb())
    cases = [
        ("Case1", "光伏逆变器输出功率15kW实测10kW"),
        ("Case2", "Modbus通信超时,寄存器无返回"),
    ]

    for name, q in cases:
        print(f"\n===== {name}: {q} =====")
        state = {
            "query": q,
            "parsed": {},
            "dept": "",
            "route_conf": 0,
            "retrieved": [],
            "search_score": 0,
            "confidence": 0,
            "result": "",
        }

        for step in asyncio.run(_stream_steps(app, state)):
            print({
                "dept": step.get("dept"),
                "route_conf": step.get("route_conf"),
                "search_score": step.get("search_score"),
                "confidence": step.get("confidence"),
                "feedback_confirmed": step.get("feedback_confirmed", False),
            })

        final = asyncio.run(app.ainvoke(state))
        print("final:", {
            "dept": final.get("dept"),
            "route_conf": final.get("route_conf"),
            "search_score": final.get("search_score"),
            "confidence": final.get("confidence"),
            "feedback_confirmed": final.get("feedback_confirmed"),
            "result": final.get("result", "")[:200],
        })


async def _stream_steps(app, state):
    """把异步流收集成列表, 供同步入口一次取用。"""
    return [step async for step in app.astream(state, stream_mode="values")]


if __name__ == "__main__":
    main()
