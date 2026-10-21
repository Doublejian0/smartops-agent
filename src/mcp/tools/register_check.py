"""mcp/tools/register_check.py - 寄存器值合法性校验(对比点表)"""

REGISTER_TABLE = {
    "40001": {"name": "有功功率", "min": 0, "max": 30000, "unit": "W"},
    "40002": {"name": "无功功率", "min": -30000, "max": 30000, "unit": "VAR"},
    "40003": {"name": "电网电压", "min": 0, "max": 500, "unit": "V"},
}

def register_check(addr, value, device_type=None):
    """校验寄存器值是否在合法范围"""
    reg = REGISTER_TABLE.get(addr)
    if not reg:
        return {"valid": False, "reason": f"地址{addr}不在点表"}
    valid = reg["min"] <= value <= reg["max"]
    return {"addr": addr, "name": reg["name"], "value": value, "valid": valid,
            "range": f"{reg['min']}~{reg['max']}{reg['unit']}" + ("" if valid else " (越限!)")}
