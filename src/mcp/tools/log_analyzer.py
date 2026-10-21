"""mcp/tools/log_analyzer.py - 日志解析工具(正则提取关键信息)"""
import re

def log_analyzer(log_text):
    """解析运维日志, 提取错误码/异常/函数/栈"""
    return {
        "error_codes": re.findall(r'ERR[_-](\d{4,6})', log_text),
        "exceptions": re.findall(r'(?i)(exception|traceback|error):?\s*(.+)', log_text),
        "functions": re.findall(r'(?<=def\s)(\w+)\(', log_text)[:20],
        "has_stack_trace": "traceback" in log_text.lower(),
    }
