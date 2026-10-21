"""agents/parser.py - 解析Agent(字段解析+校验; 追问循环在 graph 层用 interrupt)"""
from __future__ import annotations

import json
import re

from src.core.llm import get_llm, get_text
from src.core.config import MANDATORY_FIELDS, FIELD_MIN_FILLED

# V2：先从小而稳开始，先覆盖核心字段；后续按学习顺序逐步扩展
# 保留接口返回 shape 不变，先保证兼容主流程
_PARSER_TEMPLATE = (
    "解析故障,只输出JSON:\n"
    '{{"devices":"设备名", "phenomenon":"故障现象", "firmware_version":"固件版本或未知", '
    '"site":"站点/机房", "ip":"IP或空", "customer":"客户名", "severity":"高/中/低", '
    '"impact_scope":"影响范围", "timestamp":"故障时间(如无填未知)", "raw_text":"原始文本原句"}}\n'
    "问题: {query}"
)


def _safe_load_json(text: str):
    """从 LLM 文本里提取首个 JSON 字符串，失败时返回空 dict。"""
    if not text:
        return {}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    raw = m.group()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


# === 设备反推规则: 现象特征词 -> 设备名 ===
# 与 router.py 的规则互为镜像: 路由靠这些词判部门, 解析靠这些词补设备。
# 解决"LLM 不推断设备名导致字段不足误判"的问题(不同 LLM 后端推断习惯不一致)。
# 顺序即优先级(与 router.py 规则置信度一致): 高频词(功率)放最后, 防止误吞
# 如"储能电池温度偏高,充电功率自动降低"应反推储能电池而非控制器。
_DEVICE_INFER = [
    (re.compile(r"(逆变器|IGBT|MPPT|谐波|THD|绝缘|直流侧|待机功耗)"), "光伏逆变器"),
    (re.compile(r"(Modbus|485|寄存器|波特率|CRC|终端电阻|通信|丢包|掉线|轮询)"), "通信模块"),
    (re.compile(r"(SOC|BMS|电池|储能|均衡|过放|OCV|充放电)"), "储能电池"),
    (re.compile(r"(IEC.?104|104规约|遥测|总召唤|突发传送|选择.?返校|对时|ASDU|keep.?alive)"), "电网协议装置"),
    (re.compile(r"(功率|出力|调度|限值|需量|无功|充电桩|限电|多功能)"), "控制器(功率调度)"),
]


def _backfill_devices(parsed, query):
    """LLM 没提取到设备时, 用规则从现象词反推设备, 减少'信息不足'误判。"""
    if parsed.get("devices") and parsed.get("devices") != "未知":
        return parsed
    for pattern, device in _DEVICE_INFER:
        if pattern.search(query):
            parsed["devices"] = device
            break
    return parsed


async def parse(query):
    """LLM 解析故障字段 + 规则反推补全, 返回 dict。"""
    llm = get_llm()
    prompt = _PARSER_TEMPLATE.format(query=query)
    resp = await llm.ainvoke(prompt)
    parsed = _safe_load_json(get_text(resp))

    # 兜底：避免主流程拿 None
    if not isinstance(parsed, dict):
        parsed = {}

    # 规范化：未返回字段给空字符串，避免后续 `parsed.get()` 直接报错
    for field in MANDATORY_FIELDS:
        parsed.setdefault(field, "")

    # 规则反推补全设备字段(LLM 推断习惯因后端而异, 规则兜底保证确定性)
    return _backfill_devices(parsed, query)


def check_completeness(parsed):
    """校验必填字段(3选2), 返回 complete/filled/missing"""
    parsed = parsed or {}
    missing = [f for f in MANDATORY_FIELDS if not parsed.get(f) or parsed.get(f) == "未知"]
    filled = len(MANDATORY_FIELDS) - len(missing)
    return {
        "complete": filled >= FIELD_MIN_FILLED,
        "filled": filled,
        "missing": missing,
    }
