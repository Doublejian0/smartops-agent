"""agents/router.py - 路由Agent三层(规则引擎 + RAG投票 + LLM兜底)"""
import re
import json
from collections import Counter
from typing import Any, NamedTuple, Optional

from src.core.llm import get_llm, get_text
from src.core.config import DEPTS


class RouteResult(NamedTuple):
    """路由结果契约：部门 + 置信度 + 判定来源。"""
    dept: str
    conf: float
    source: str  # "rule" | "rag_vote" | "llm"

RULES = [
    # 边界/模糊场景优先收口，避免被“功率/出力”等高频词误拉到控制器
    (re.compile(r"(设备异常|多个系统同时出问题|功率异常加通信丢包|控制器还是逆变器|不清楚.*(控制器|逆变器|通信|储能)|说不清)", re.IGNORECASE), "不确定", 0.95),
    (re.compile(r"modbus.*(超时|timeout|无返回|失败|CRC|校验|写值.*不一致|读回.*不一致|寄存器.*(映射|地址)|波特率|485|终端电阻|轮询周期|丢包|缓存)", re.IGNORECASE), "通信硬件组", 0.93),
    (re.compile(r"IEC.?104.*(不通|超时|规约|链路|遥测|总召唤|突发传送|选择.?返校|对时|ASDU|信息体地址|keep.?alive)", re.IGNORECASE), "电网协议组", 0.92),
    (re.compile(r"(SOC|储能).*(跳变|异常|偏差|电量|校准|卡死|估算|均衡|过放|降额|充电功率.*降低|温度.*偏高|BMS.*(估算|校准)|OCV|计数)", re.IGNORECASE), "储能部门", 0.92),
    (re.compile(r"(功率|出力).*(限值|调度|不符|实测|低于|不足|偏低|异常波动|波动|多功能|互斥|充电桩|无功补偿|偏差|恢复|限电保护|需量管理|调度策略)", re.IGNORECASE), "控制器部门", 0.85),
    (re.compile(r"逆变器.*(过温|IGBT|故障|降额|绝缘|阻抗|谐波|THD|MPPT|待机功耗|辅助电源|电压采样|直流侧.*波动)", re.IGNORECASE), "逆变器硬件组", 0.94),
]


def route_rule(query: str) -> Optional[RouteResult]:
    """规则层：支持多规则命中，返回权重最高的一条。"""
    matched: list[RouteResult] = []
    for pattern, dept, conf in RULES:
        if pattern.search(query):
            matched.append(RouteResult(dept, conf, "rule"))

    if not matched:
        return None

    # 同时命中时取 conf 最大；若 conf 并列取第一个
    matched.sort(key=lambda x: x.conf, reverse=True)
    return matched[0]


def route_rag_vote(query: str, collection: Any, n: int = 5) -> tuple[Optional[str], float, Counter]:
    """RAG 投票：查询命中最多的 dept 且满足阈值。

    返回 (dept, conf, counter)：
      - dept 有值 = 投票成功
      - dept=None = 投票失败（平票/票数不足），counter 保留分布供 LLM 仲裁
    """
    if not collection:
        return None, 0, Counter()

    try:
        res = collection.query(query_texts=[query], n_results=n)
        metadatas = res.get("metadatas", [[]])[0] or []
    except Exception:
        return None, 0, Counter()

    depts = [m.get("dept", "") for m in metadatas if isinstance(m, dict)]
    counter = Counter(depts)
    if not counter:
        return None, 0, counter

    top, count = counter.most_common(1)[0]
    min_count = max(3, n // 2)
    if count >= min_count and top:
        return top, round(count / n * 0.8, 2), counter

    return None, 0, counter


async def route_llm(query: str, vote_context: Optional[Counter] = None) -> RouteResult:
    """LLM兜底：返回结构化 dept。可传入投票分布，让 LLM 做有信息的仲裁。"""
    llm = get_llm()

    if vote_context:
        top_items = vote_context.most_common(3)
        vote_desc = "、".join(f"{d}({c}票)" for d, c in top_items)
        prompt = (
            "判断故障归属部门,只输出JSON: {\"dept\":\"部门\", \"reason\":\"判定依据\"}\n"
            f"部门列表:{DEPTS}\n"
            f"知识库投票结果(平票或票数不足,供参考):{vote_desc}\n"
            f"故障:{query}"
        )
    else:
        prompt = (
            "判断故障归属部门,只输出JSON: {\"dept\":\"部门\", \"reason\":\"判定依据\"}\n"
            f"部门列表:{DEPTS}\n故障:{query}"
        )

    resp = await llm.ainvoke(prompt)
    m = re.search(r"\{.*\}", get_text(resp), re.DOTALL)
    d = json.loads(m.group()) if m else {}

    dept = d.get("dept", "不确定")
    if dept not in DEPTS:
        dept = "不确定"

    return dept, 0.40, "llm"


async def route(query, collection=None):
    """三层漏斗: 规则 -> RAG投票 -> LLM兜底。投票失败时把分布传给 LLM 仲裁。"""
    r = route_rule(query)
    if r:
        return r

    if collection is not None:
        dept, conf, counter = route_rag_vote(query, collection)
        if dept:
            return dept, conf, "rag_vote"
        if counter:  # 投票失败但保留了分布，传给 LLM 做有信息的仲裁
            return await route_llm(query, vote_context=counter)

    return await route_llm(query)

