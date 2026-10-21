"""
V1-7 MCP工具: log_analyzer + register_check(架构图5)
先实现工具函数逻辑; FastMCP封装成MCP server(stdio)供Agent调用是工程化步骤

运行: smartops-agent/.venv/Scripts/python.exe notebooks/mcp_tools_demo.py
"""
import re

# === log_analyzer: 日志解析(正则提取错误码/异常/函数/栈)===(架构图5实现示例)
def log_analyzer(log_text):
    error_codes = re.findall(r'ERR[_-](\d{4,6})', log_text)
    exceptions = re.findall(r'(?i)(exception|traceback|error):?\s*(.+)', log_text)
    functions = re.findall(r'(?<=def\s)(\w+)\(', log_text)
    return {
        "error_codes": error_codes,
        "exceptions": [{"type": e[0], "msg": e[1].strip()[:100]} for e in exceptions],
        "functions": functions[:20],
        "has_stack_trace": "traceback" in log_text.lower(),
    }

# === register_check: 寄存器值合法性校验(对比点表)===
REGISTER_TABLE = {
    "40001": {"name": "有功功率", "min": 0, "max": 30000, "unit": "W"},
    "40002": {"name": "无功功率", "min": -30000, "max": 30000, "unit": "VAR"},
    "40003": {"name": "电网电压", "min": 0, "max": 500, "unit": "V"},
}
def register_check(addr, value, device_type=None):
    reg = REGISTER_TABLE.get(addr)
    if not reg:
        return {"valid": False, "reason": f"地址{addr}不在点表"}
    valid = reg["min"] <= value <= reg["max"]
    return {"addr": addr, "name": reg["name"], "value": value, "valid": valid,
            "range": f"{reg['min']}~{reg['max']}{reg['unit']}" + ("" if valid else " (越限!)")}

# === 演示 ===
print("=== log_analyzer: 解析运维日志 ===")
log = """[2025-08-01] ERR_1024 功率调度异常
Traceback: ValueError in dispatch_power()
def dispatch_power(): set limit=15kW
Exception: register 40001 read timeout"""
for k, v in log_analyzer(log).items():
    print(f"  {k}: {v}")

print("\n=== register_check: 校验寄存器值 ===")
print("  40001=15000:", register_check("40001", 15000))    # 正常
print("  40001=35000:", register_check("40001", 35000))    # 越限
print("  40099=100  :", register_check("40099", 100))      # 不在点表

print("\n✅ MCP工具: log_analyzer(日志解析)+ register_check(寄存器校验)")
print("  (FastMCP封装成MCP server/stdio供Agent调用 = 架构图5, 工程化步骤)")
