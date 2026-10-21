"""
api/main.py - FastAPI 服务(把诊断系统暴露成 API, V2 生产化基础)
启动: cd smartops-agent && HF_HUB_OFFLINE=1 .venv/Scripts/python.exe -m uvicorn src.api.main:app --port 8000 --reload
"""
import os
os.environ['HF_HUB_OFFLINE'] = '1'
from fastapi import FastAPI, Depends
from pydantic import BaseModel

from src.rag.embedding import get_or_create_collection
from src.orchestration.graph import build_graph

app = FastAPI(title="SmartOps 故障诊断", version="V2")

# === 启动时建库 + 构建图 ===
DEPT_MAP = {"功率调度": "控制器部门", "储能": "储能部门", "通信": "通信硬件组",
            "电网协议": "电网协议组", "逆变器": "逆变器硬件组"}
docs = [
    ("光伏逆变器输出功率低于设定值,dispatch_power()限值逻辑", "功率调度"),
    ("功率限值触发:电网调度指令、需量管理、限电保护", "功率调度"),
    ("储能电池SOC跳变,BMS通信正常", "储能"),
    ("Modbus通信超时,寄存器地址、波特率、终端电阻", "通信"),
    ("IEC104协议不通,TCP2404端口,ASDU地址配置", "电网协议"),
    ("逆变器过温停机,IGBT温度超阈值,降额保护", "逆变器"),
]
kb = get_or_create_collection("api_kb",
    [(d, {"id": f"d{i}", "domain": dom, "dept": DEPT_MAP[dom]}) for i, (d, dom) in enumerate(docs)])
_graph = build_graph(kb)


async def get_graph():
    """依赖注入：把诊断图作为依赖提供给路由。

    好处：路由显式声明"我需要 graph"，测试时可替换，依赖可管理生命周期。
    """
    return _graph


class DiagnoseRequest(BaseModel):
    query: str


class FeedbackRequest(BaseModel):
    diag_id: str
    corrected_dept: str = ""
    root_cause: str = ""


@app.post("/diagnose")
async def diagnose(req: DiagnoseRequest, graph=Depends(get_graph)):
    """诊断接口: POST 故障描述 -> 返回路由/置信度/分支/结果

    V2 新增: 门卫出口时返回 status=rejected|needs_clarification,
    调用方程序可先判断 status 再决定是否继续处理诊断结果。
    """
    r = await graph.ainvoke({"query": req.query, "parsed": {}, "dept": "", "route_conf": 0,
                             "retrieved": [], "search_score": 0, "confidence": 0, "result": ""})

    # 门卫出口: 拒绝 / 反问
    if r["dept"] in ("拒绝", "待补全"):
        return {
            "query": req.query,
            "status": "rejected" if r["dept"] == "拒绝" else "needs_clarification",
            "message": r["result"],
            "dept": r["dept"],
            "diagnosis_id": r.get("diagnosis_id", "N/A"),
        }

    return {
        "query": req.query,
        "status": "ok",
        "dept": r["dept"],
        "confidence": round(r["confidence"], 3),
        "branch": "ticket(工单)" if r["confidence"] >= 0.7 else "expert(专家)",
        "result": r["result"][:500],
        "diagnosis_id": r.get("diagnosis_id", "N/A"),
    }


@app.post("/feedback")
async def feedback(req: FeedbackRequest, graph=Depends(get_graph)):
    """人工反馈回写接口：修正归属/补充根因后回写知识库"""
    await graph.ainvoke({
        "query": "",
        "parsed": {},
        "dept": req.corrected_dept or "控制器部门",
        "route_conf": 0,
        "retrieved": [],
        "search_score": 0,
        "confidence": 0,
        "result": "",
        "diagnosis_id": req.diag_id,
        "feedback_confirmed": True,
        "feedback_dept": req.corrected_dept,
        "feedback_root_cause": req.root_cause,
    })
    return {
        "status": "ok",
        "msg": "已接收反馈并回写知识库",
        "diagnosis_id": req.diag_id,
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "SmartOps-V2"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)   # 右键Run启动服务
