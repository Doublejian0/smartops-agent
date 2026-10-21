"""core/moderation.py - 门卫模块: 内容安全拦截(涉政涉黄违法) + 模糊 query 初筛

作用: 在正式诊断前加一道"门卫", 拦下两类不该进主流程的输入:
1. 敏感/违规内容 -> 直接拒绝(不回显原文)
2. 过于模糊的 query(如"光伏出问题了") -> 反问补全

设计原则:
- 纯规则、确定性、零 LLM 调用(可审计、零延迟、零成本)
- 这是第一道粗筛; 更细的判定由 parse 后的字段完整率检查(3选2)兜底
- 词表可随时增删, 不需要改图结构
"""
import re

# === 1. 敏感词规则: (pattern, 命中原因) ===
# 只拦明显违规内容; 正常运维术语不受影响。
SENSITIVE_PATTERNS = [
    (re.compile(r"(赌博|赌球|博彩|下注|六合彩|百家乐|老虎机)"), "涉赌内容"),
    (re.compile(r"(招嫖|嫖娼|卖淫|约炮|裸聊|色情|成人视频|黄片)"), "涉黄内容"),
    (re.compile(r"(毒品|冰毒|海洛因|大麻|摇头丸|制毒|贩毒)"), "涉毒内容"),
    (re.compile(r"(买枪|枪支|弹药|炸药|雷管|管制刀具)"), "涉危险品"),
    (re.compile(r"(诈骗|洗钱|代开发票|办假证|刷单兼职|出售银行卡|黑产)"), "涉违法内容"),
    (re.compile(r"(颠覆国家|煽动叛乱|暴恐|恐怖袭击|法轮功|邪教)"), "涉政敏感"),
]

# === 2. 具体设备关键词 ===
# 注意: 故意不放"光伏"——"光伏出问题了"里的光伏是领域统称,
# 不知道具体指逆变器还是储能, 所以算模糊。
DEVICE_KEYWORDS = [
    "逆变器", "储能", "充电桩", "通信", "控制器", "PCS", "BMS",
    "Modbus", "IEC104", "电池", "电表", "并网柜", "汇流箱", "开关柜",
]


def check_sensitive(text: str):
    """命中敏感词返回原因字符串, 否则返回 None。"""
    for pattern, reason in SENSITIVE_PATTERNS:
        if pattern.search(text):
            return reason
    return None


def is_vague(text: str) -> bool:
    """规则判断 query 是否过于模糊。

    判定: 很短(<8字) 且 没有具体设备关键词 -> 视为"光伏出问题了"这类笼统描述。
    例:
      "光伏出问题了" -> 6字无设备 -> 模糊
      "设备异常"     -> 4字无设备 -> 模糊
      "逆变器坏了"   -> 有"逆变器" -> 不模糊(交给 parse 校验字段)
      "光伏功率15kW实测10kW" -> 长度够 -> 不模糊
    """
    text = (text or "").strip()
    if len(text) >= 8:
        return False
    if any(k in text for k in DEVICE_KEYWORDS):
        return False
    return True


def classify(text: str) -> dict:
    """门卫总入口。

    返回 {"verdict": "rejected" | "needs_clarification" | "allowed", "reason": str}
    """
    reason = check_sensitive(text)
    if reason:
        return {"verdict": "rejected", "reason": reason}
    if is_vague(text):
        return {"verdict": "needs_clarification", "reason": "故障描述过于模糊"}
    return {"verdict": "allowed", "reason": ""}
