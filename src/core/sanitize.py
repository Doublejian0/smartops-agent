"""core/sanitize.py - 输入自动脱敏（IP / 设备SN / 客户名 / 联系方式）"""
import re

# 脱敏规则: (pattern, 替换文本, 描述)
RULES = [
    # IPv4 地址 → [IP]
    (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'), '[IP地址]', 'IP地址'),
    # 设备序列号: 常见格式 SN:XXX / S/N:XXX / ESN:XXX
    (re.compile(r'(?:SN|S/N|ESN|序列号)\s*[:：]\s*\S+', re.IGNORECASE), 'SN:[已脱敏]', '设备序列号'),
    # MAC 地址
    (re.compile(r'\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b'), '[MAC地址]', 'MAC地址'),
    # 手机号(中国大陆)
    (re.compile(r'\b1[3-9]\d{9}\b'), '[手机号]', '手机号'),
    # 固话/座机
    (re.compile(r'\b0\d{2,3}-?\d{7,8}\b'), '[座机]', '座机号'),
    # 邮箱
    (re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b'), '[邮箱]', '邮箱'),
    # 客户名: "客户: XXX" / "客户名称: XXX"
    (re.compile(r'((?:客户(?:名称)?|联系人)\s*[:：]\s*)\S+', re.IGNORECASE), r'\1[已脱敏]', '客户名'),
]

def sanitize(text: str) -> str:
    """对输入文本做自动脱敏, 返回脱敏后文本"""
    for pattern, replacement, _desc in RULES:
        text = pattern.sub(replacement, text)
    return text

def sanitize_dict(data: dict, fields: list = None) -> dict:
    """对 dict 中指定字段做脱敏, 默认脱敏所有 str 值"""
    result = {}
    for k, v in data.items():
        if isinstance(v, str) and (fields is None or k in fields):
            result[k] = sanitize(v)
        elif isinstance(v, dict):
            result[k] = sanitize_dict(v, fields)
        elif isinstance(v, list):
            result[k] = [sanitize_dict(i, fields) if isinstance(i, dict) else sanitize(str(i)) if isinstance(i, str) else i for i in v]
        else:
            result[k] = v
    return result
