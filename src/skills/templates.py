"""skills/templates.py - 5个Skill模板(结构化排查指引)"""
SKILLS = [
    {"name": "功率不符排查", "domain": "功率调度", "keywords": ["功率", "出力", "不符", "低于"],
     "steps": ["查参数配置(-> knowledge_search)", "查调度策略(-> knowledge_search)", "查限电保护",
               "校验Modbus寄存器(-> register_check)", "分析日志(-> log_analyzer)"]},
    {"name": "Modbus通信异常", "domain": "通信", "keywords": ["Modbus", "通信", "超时", "寄存器"],
     "steps": ["物理连接与终端电阻", "波特率校验", "寄存器合法性(-> register_check)", "抓包分析", "固件兼容"]},
    {"name": "储能充放电异常", "domain": "储能", "keywords": ["储能", "SOC", "充放电", "BMS"],
     "steps": ["查SOC限值", "查电价策略", "查电池保护", "BMS通信校验"]},
    {"name": "电网协议对接", "domain": "电网协议", "keywords": ["IEC104", "协议", "遥测", "遥控"],
     "steps": ["查TCP2404端口", "查ASDU地址", "查召唤标志位", "查选择-返校-执行"]},
    {"name": "多功能耦合异常", "domain": "功率调度", "keywords": ["多功能", "耦合", "冲突", "同时"],
     "steps": ["列功能清单", "逐项关闭排查", "查互斥逻辑"]},
]
