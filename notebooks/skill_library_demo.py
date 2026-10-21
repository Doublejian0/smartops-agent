"""
V1-4 Skill库: 5个结构化排查模板 + matcher
对应架构图6: V1做静态清单(分步排查+关联工具), V2再升级子工作流

运行: smartops-agent/.venv/Scripts/python.exe notebooks/skill_library_demo.py
"""

# === 5个Skill模板(每个: 名称/域/关键词/分步排查[关联工具])===
SKILLS = [
    {
        "name": "功率不符排查",
        "domain": "功率调度",
        "keywords": ["功率", "出力", "不符", "低于"],
        "steps": [
            "查参数配置(-> knowledge_search('功率上限参数'))",
            "查调度策略是否占用(-> knowledge_search('调度策略 功率分配'))",
            "查电网限电保护触发条件(-> knowledge_search('限电保护'))",
            "校验Modbus寄存器值(-> register_check(addr, value))",
            "分析功率模块日志(-> log_analyzer(log_text))",
        ],
    },
    {
        "name": "Modbus通信异常",
        "domain": "通信",
        "keywords": ["Modbus", "通信", "超时", "寄存器"],
        "steps": [
            "物理连接与终端电阻检查",
            "波特率/奇偶校验配置校验",
            "寄存器地址合法性校验(-> register_check(addr))",
            "抓包帧分析",
            "固件版本兼容性排查(-> knowledge_search(version=当前版本))",
        ],
    },
    {
        "name": "储能充放电异常",
        "domain": "储能",
        "keywords": ["储能", "SOC", "充放电", "BMS"],
        "steps": [
            "查SOC上下限设定(-> knowledge_search('SOC限值 充放电策略'))",
            "查电价时段策略干预",
            "查电池保护状态触发条件",
            "BMS通信状态校验",
        ],
    },
    {
        "name": "电网协议对接",
        "domain": "电网协议",
        "keywords": ["IEC104", "协议", "遥测", "遥控"],
        "steps": [
            "查TCP 2404端口连通",
            "查ASDU地址/信息体地址配置",
            "查召唤/突发传送标志位",
            "查选择-返校-执行流程",
        ],
    },
    {
        "name": "多功能耦合异常",
        "domain": "功率调度",
        "keywords": ["多功能", "耦合", "冲突", "同时"],
        "steps": [
            "列出当前开启功能清单",
            "逐项关闭排查冲突源",
            "查功能间优先级/互斥逻辑(-> knowledge_search('功能互斥 优先级'))",
        ],
    },
]

# === matcher: 关键词+domain匹配故障到Skill ===
def skill_match(query, domain=None):
    best, best_score = None, 0
    for skill in SKILLS:
        score = sum(1 for k in skill["keywords"] if k in query)   # 关键词命中数
        if domain and skill["domain"] == domain:
            score += 2    # domain匹配加权
        if score > best_score:
            best, best_score = skill, score
    return best, best_score

# === 测试: 给故障, 匹配Skill, 输出排查步骤 ===
test_cases = [
    ("光伏输出功率15kW实测10kW", "功率调度"),
    ("Modbus通信超时,寄存器无返回", "通信"),
    ("储能电池SOC跳变", "储能"),
]
for query, domain in test_cases:
    skill, score = skill_match(query, domain)
    print(f"故障: 「{query}」 (domain={domain})")
    print(f"  -> 匹配Skill: {skill['name']} (匹配分={score})")
    for i, step in enumerate(skill["steps"], 1):
        print(f"     {i}. {step}")
    print()

print("✅ Skill库: 5模板 + matcher(关键词+domain匹配), 返回分步排查指引")
print("  (V2升级: 这些步骤里的工具调用由Agent自动执行, 变成子工作流)")
