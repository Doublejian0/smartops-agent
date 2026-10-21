"""orchestration/graph.py - LangGraph V2 编排（回写闭环 + 脱敏 + 同义词 + 多轮追问）"""
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
from src.core.config import CONFIDENCE_THRESHOLD, ROUTE_WEIGHT, SEARCH_WEIGHT, MAX_ASK_ROUNDS
from src.core.moderation import classify
from src.core.sanitize import sanitize
from src.core.synonym_dict import normalize
from src.agents.parser import parse, check_completeness
from src.agents.router import route
from src.rag.retrieval import retrieve
from src.agents.ticket_gen import gen_ticket
from src.core.llm import get_llm, get_text
from src.storage import db
import json, uuid
from datetime import datetime

class DiagState(TypedDict, total=False):
    query: str
    raw_query: str               # 脱敏前原文
    parsed: dict
    dept: str
    route_conf: float
    retrieved: list
    search_score: float
    confidence: float
    result: str
    # === V2 新增: 人工反馈 ===
    feedback_dept: Optional[str]      # 人工修正归属
    feedback_root_cause: Optional[str] # 人工补充根因
    feedback_confirmed: bool           # 人工确认标记
    diagnosis_id: str                  # 本次诊断唯一ID
    # === V2 新增: 门卫(安全拦截 + 模糊反问) ===
    moderation_verdict: str            # allowed / rejected / needs_clarification
    moderation_reason: str             # 拒绝原因(命中敏感词时)
    ask_round: int                     # 追问轮数(多轮会话)

_kb = None

def _sanitize_node(state):
    """入口脱敏 + 同义词标准化"""
    raw = state["query"]
    cleaned = normalize(sanitize(raw))
    return {
        "raw_query": raw,
        "query": cleaned,
        "diagnosis_id": f"diag-{uuid.uuid4().hex[:8]}",
        "feedback_confirmed": False,
    }

async def _parse_node(state):
    return {"parsed": await parse(state["query"])}

# === V2 新增: 门卫节点(安全拦截 + 模糊反问, 纯规则不调 LLM) ===
def _moderate_node(state):
    """门卫: 对脱敏后的 query 做敏感词拦截 + 模糊初筛"""
    m = classify(state["query"])
    return {"moderation_verdict": m["verdict"], "moderation_reason": m["reason"]}

def _after_moderate(state):
    """三个出口: rejected -> 拒绝 | needs_clarification -> 反问 | allowed -> 解析"""
    return state["moderation_verdict"]

def _reject_node(state):
    """拒绝回复。注意: 不回显敏感原文。"""
    return {"result": f"🚫 无法受理: {state['moderation_reason']}", "dept": "拒绝"}

def _clarify_text_node(state):
    """反问补全(单次诊断)：返回反问文本，END。"""
    chk = check_completeness(state.get("parsed", {}))
    field_cn = {
        "devices": "具体设备(逆变器/储能电池/充电桩/通信模块/控制器)",
        "phenomenon": "故障现象(功率偏低/通信超时/过温停机等)",
        "firmware_version": "固件版本(不确定可填'未知')",
    }
    tips = "、".join(field_cn.get(f, f) for f in chk["missing"]) or "设备、现象与固件版本"
    return {
        "result": (
            "🤔 故障描述不够具体, 暂无法诊断, 请补充后重试:\n"
            f"需补充: {tips}\n"
            "示例: 『光伏逆变器输出功率15kW、实测10kW、固件V2.3.1』"
        ),
        "dept": "待补全",
    }


def _clarify_interrupt_node(state):
    """反问补全(多轮会话)：interrupt 暂停等待用户补充。"""
    chk = check_completeness(state.get("parsed", {}))
    field_cn = {
        "devices": "具体设备(逆变器/储能电池/充电桩/通信模块/控制器)",
        "phenomenon": "故障现象(功率偏低/通信超时/过温停机等)",
        "firmware_version": "固件版本(不确定可填'未知')",
    }
    tips = "、".join(field_cn.get(f, f) for f in chk["missing"]) or "设备、现象与固件版本"

    user_reply = interrupt({
        "question": f"需补充: {tips}",
        "hint": "示例: 光伏逆变器输出功率15kW、实测10kW、固件V2.3.1",
    })

    # 用户补充后: query 用补充替换(诊断要清晰，避免"设备异常"等模糊词残留干扰路由)，
    # raw_query 记录完整历史(回写/落库要保留上下文)
    return {
        "query": user_reply,
        "raw_query": f"{state.get('raw_query', '')} {user_reply}".strip(),
        "ask_round": state.get("ask_round", 0) + 1,
    }

def _after_parse(state):
    """解析后字段不足(3选2不满足)且追问未超轮数 -> 反问; 否则进入路由(硬着头皮诊断)"""
    chk = check_completeness(state.get("parsed", {}))
    if not chk["complete"] and state.get("ask_round", 0) < MAX_ASK_ROUNDS:
        return "clarify"
    return "route"

def _after_start(state):
    """反馈回写是第二条入口: 带 feedback_confirmed=True 时跳过诊断链路直接回写"""
    return "feedback" if state.get("feedback_confirmed") else "sanitize"

async def _route_node(state):
    dept, conf, _ = await route(state["query"], _kb)
    return {"dept": dept, "route_conf": conf}

async def _search_node(state):
    retrieved = await retrieve(state["query"], _kb)
    min_dist = min((d[2] for d in retrieved), default=0.5)
    return {"retrieved": retrieved, "search_score": max(0, 1 - min_dist)}

def _confidence_node(state):
    conf = state["route_conf"] * ROUTE_WEIGHT + state["search_score"] * SEARCH_WEIGHT
    return {"confidence": conf}

def _after_conf(state):
    return "ticket" if state["confidence"] >= CONFIDENCE_THRESHOLD else "expert"

async def _ticket_node(state):
    ticket = await gen_ticket(state["query"], state["dept"], state["retrieved"])
    return {"result": ticket.model_dump_json(ensure_ascii=False) if ticket else "工单生成失败"}

async def _expert_node(state):
    resp = await get_llm().ainvoke(
        f'故障归属不确定,给2条排查建议,简答。故障:{state["query"]}\n'
        f'路由结果:{state["dept"]}(置信度{state["route_conf"]})\n'
        f'检索结果:{state.get("retrieved",[])}')
    return {"result": get_text(resp)}

# === V2 新增: 反馈回写节点 ===
def _feedback_node(state):
    """
    人工确认后的回写节点。
    1. 诊断记录落 SQLite(真相源, 供统计/追溯)——无论是否反馈确认都要留痕
    2. 当 feedback_confirmed=True 时, 修正案例回写 ChromaDB + 反馈审计落库
    """
    _save_diagnosis_record(state)

    if not state.get("feedback_confirmed"):
        return {"result": state.get("result", "") + "\n[待人工确认]"}

    corrected_dept = state.get("feedback_dept") or state["dept"]
    root_cause = state.get("feedback_root_cause", "")
    query = state.get("raw_query", state["query"])

    # 构建回写文档
    doc_text = f"故障:{query}\n根因:{root_cause}\n归属:{corrected_dept}"
    meta = {
        "id": state.get("diagnosis_id", "unknown"),
        "dept": corrected_dept,
        "domain": corrected_dept,
        "root_cause": root_cause,
        "source": "human_feedback",
        "created_at": datetime.now().isoformat(),
    }
    doc_id = f"fb_{state.get('diagnosis_id', uuid.uuid4().hex[:8])}"

    try:
        _kb.upsert(documents=[doc_text], metadatas=[meta], ids=[doc_id])
        # 反馈审计落 SQLite(谁在何时改了什么)
        db.save_feedback({
            "diagnosis_id": state.get("diagnosis_id", "unknown"),
            "corrected_dept": corrected_dept,
            "root_cause": root_cause,
        })
        print(f"  [回写] 案例 {doc_id} 已写入知识库 (dept={corrected_dept})")
    except Exception as e:
        print(f"  [回写失败] {e}")

    result = state.get("result", "")
    return {"result": result + f"\n[✅ 已确认, 案例已回写知识库]",
            "feedback_dept": corrected_dept}


def _save_diagnosis_record(state):
    """把诊断结果写入 SQLite(真相源), 供统计/追溯/审计。"""
    try:
        db.save_diagnosis({
            "diagnosis_id": state.get("diagnosis_id", ""),
            "query": state.get("raw_query", state.get("query", "")),
            "parsed": state.get("parsed", {}),
            "dept": state.get("dept", ""),
            "route_conf": state.get("route_conf", 0),
            "search_score": state.get("search_score", 0),
            "confidence": state.get("confidence", 0),
            "branch": "ticket" if state.get("confidence", 0) >= CONFIDENCE_THRESHOLD else "expert",
            "result": state.get("result", ""),
            "status": "done",
        })
    except Exception as e:
        print(f"  [落库失败] {e}")

def _after_feedback(state):
    """确认后结束, 否则等待"""
    return END  # 当前版本直接结束; 后续可加 human-in-the-loop

def build_graph(kb, checkpointer=None):
    """构建 V2 编排图, 传入知识库 collection。

    checkpointer: 需要多轮会话时传 MemorySaver()/SqliteSaver()；单次诊断传 None(默认)。
    """
    global _kb
    _kb = kb
    g = StateGraph(DiagState)

    # clarify 节点：多轮(checkpointer)用 interrupt，单次用反问文本
    clarify_node = _clarify_interrupt_node if checkpointer is not None else _clarify_text_node

    nodes = [
        ("sanitize", _sanitize_node),
        ("moderate", _moderate_node),      # V2 新增: 门卫
        ("reject", _reject_node),          # V2 新增: 拒绝出口
        ("clarify", clarify_node),         # 多轮 interrupt / 单次反问文本
        ("parse", _parse_node),
        ("route", _route_node),
        ("search", _search_node),
        ("confidence", _confidence_node),
        ("ticket", _ticket_node),
        ("expert", _expert_node),
        ("feedback", _feedback_node),  # V2 新增
    ]
    for name, fn in nodes:
        g.add_node(name, fn)

    # V2 链路: START → (feedback 回写直达 | sanitize → moderate → (reject | clarify | parse) → (clarify | route))
    #         → search → confidence → (ticket | expert) → feedback → END
    g.add_conditional_edges(START, _after_start, {"feedback": "feedback", "sanitize": "sanitize"})
    g.add_edge("sanitize", "moderate")
    g.add_conditional_edges("moderate", _after_moderate, {
        "rejected": "reject",
        "needs_clarification": "clarify",
        "allowed": "parse",
    })
    g.add_conditional_edges("parse", _after_parse, {
        "clarify": "clarify",
        "route": "route",
    })
    g.add_edge("reject", END)
    if checkpointer is not None:
        g.add_edge("clarify", "parse")   # 多轮：追问后重新解析
    else:
        g.add_edge("clarify", END)       # 单次：反问后结束
    g.add_edge("route", "search")
    g.add_edge("search", "confidence")
    g.add_conditional_edges("confidence", _after_conf, {"ticket": "ticket", "expert": "expert"})
    g.add_edge("ticket", "feedback")
    g.add_edge("expert", "feedback")
    g.add_edge("feedback", END)

    # checkpointer 持久化会话状态: 同一个 thread_id 的多轮 invoke 共享状态
    return g.compile(checkpointer=checkpointer)
