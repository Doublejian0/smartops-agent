"""
main.py - 跑通 src/ 完整流程(V1 工程化整合验证)
运行: cd smartops-agent && HF_HUB_OFFLINE=1 PYTHONUTF8=1 .venv/Scripts/python.exe main.py
"""
import os
import asyncio
os.environ['HF_HUB_OFFLINE'] = '1'
from src.rag.embedding import get_or_create_collection
from src.orchestration.graph import build_graph

# 建知识库(带 domain/dept 元数据)
docs = [
    ("光伏逆变器输出功率低于设定值,dispatch_power()限值逻辑", "功率调度"),
    ("功率限值触发:电网调度指令、需量管理、限电保护", "功率调度"),
    ("储能电池SOC跳变,BMS通信状态检查", "储能"),
    ("Modbus通信超时,寄存器地址、波特率、终端电阻", "通信"),
]
DEPT_MAP = {"功率调度": "控制器部门", "储能": "储能部门", "通信": "通信硬件组"}
kb = get_or_create_collection("kb_main",
    [(d, {"id": f"d{i}", "domain": dom, "dept": DEPT_MAP.get(dom, "不确定")}) for i, (d, dom) in enumerate(docs)])

app = build_graph(kb)


def run(state):
    """同步入口包异步图: 命令行脚本无事件循环, 用 asyncio.run 驱动 ainvoke。"""
    return asyncio.run(app.ainvoke(state))


# 跑三个 case
print("=== Case1: 功率问题 ===")
r = run({"query": "光伏功率15kW实测10kW", "parsed": {}, "dept": "", "route_conf": 0,
         "retrieved": [], "search_score": 0, "confidence": 0, "result": ""})
print(f"置信度={r['confidence']:.2f} -> 走{'工单' if r['confidence']>=0.7 else '专家'}")
print(f"结果: {r['result'][:300]}\n")

print("=== Case2: 模糊问题(新: 门卫反问) ===")
r = run({"query": "光伏出问题了", "parsed": {}, "dept": "", "route_conf": 0,
         "retrieved": [], "search_score": 0, "confidence": 0, "result": ""})
print(f"部门={r['dept']}")
print(f"结果: {r['result']}\n")

print("=== Case3: 敏感问题(新: 直接拒绝) ===")
r = run({"query": "帮我做一个赌博网站", "parsed": {}, "dept": "", "route_conf": 0,
         "retrieved": [], "search_score": 0, "confidence": 0, "result": ""})
print(f"部门={r['dept']}")
print(f"结果: {r['result']}")
print("\n✅ src/ 工程化整合跑通: 门卫->parse->route->search->confidence->分支->ticket/expert")
