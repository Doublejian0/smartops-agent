"""core/prompt_templates.py - Prompt 模板版本管理 + A/B 测试支持"""
from typing import Dict

# 模板注册表: {template_name: {version: prompt_string}}
TEMPLATES: Dict[str, Dict[str, str]] = {}

def register(name: str, version: str, template: str):
    """注册一个 prompt 模板版本"""
    TEMPLATES.setdefault(name, {})[version] = template

def get(name: str, version: str = None) -> str:
    """获取模板, version=None 取最新版本"""
    versions = TEMPLATES.get(name, {})
    if not versions:
        raise KeyError(f"模板 '{name}' 不存在")
    if version:
        return versions[version]
    # 取版本号最大的(按字符串排序, 适合 "v1"/"v2" 等)
    latest = sorted(versions.keys())[-1]
    return versions[latest]

def list_versions(name: str) -> list:
    """列出某模板的所有版本"""
    return sorted(TEMPLATES.get(name, {}).keys())

# ============================================================
#  解析 Agent — 故障字段提取
# ============================================================
register("parse", "v1", """解析故障描述,提取结构化字段。只输出JSON:
{{"devices":"设备名称","phenomenon":"故障现象","firmware_version":"固件版本或未知"}}

问题: {query}""")

register("parse", "v2", """你是SmartHEMS(光伏+储能)运维专家。从故障描述中提取结构化字段。
只输出JSON,不要markdown包裹:
{{"devices":"涉及的具体设备","phenomenon":"故障现象描述","firmware_version":"固件版本,未知填unknown"}}

故障描述: {query}""")

# ============================================================
#  路由 Agent — LLM 兜底判定
# ============================================================
register("route_llm", "v1", """判断故障归属部门,只输出JSON:{{"dept":"部门"}}
部门列表:{depts}
故障:{query}""")

register("route_llm", "v2", """你是SmartHEMS运维调度专家。判断以下故障归属哪个技术部门。
只输出JSON,不要markdown:
{{"dept":"部门名","reason":"判定依据(一句话)"}}

可选部门: {depts}
故障描述: {query}
解析结果: {parsed}""")

# ============================================================
#  多查询生成 — 检索扩写
# ============================================================
register("multi_query", "v1", """SmartHEMS(光伏+储能)运维检索助手。扩写成{n}个检索查询,每行一个,不要编号:
{query}""")

register("multi_query", "v2", """你是SmartHEMS运维知识检索助手。将用户口语化问题扩写为{n}个标准检索查询。
要求: ①标准化术语 ②从根因角度重述 ③关注细节字段
每行一个查询,不要编号和markdown:

用户问题: {query}""")

# ============================================================
#  工单生成 Agent
# ============================================================
register("ticket_gen", "v1", """根据故障和知识库生成工单,只输出JSON(不要markdown):
{{"title":"","product_version":"SmartHEMS V3.2.1","severity":"高/中/低","description":"","preliminary_analysis":"","suggested_dept":"{dept}","related_cases":[]}}
知识库:
{context}
故障:{query}""")

register("ticket_gen", "v2", """你是SmartHEMS运维工单起草助手。基于知识库和历史案例,生成标准结构化工单。
只输出JSON,严格7个字段,不要markdown包裹:
{{
  "title": "[归属部门] 故障简述",
  "product_version": "SmartHEMS V3.2.1",
  "severity": "高/中/低",
  "description": "故障现象+已排查项+排除项",
  "preliminary_analysis": "疑似根因+依据(引用知识库)",
  "suggested_dept": "{dept}",
  "related_cases": ["案例ID1","案例ID2"]
}}
知识库参考:
{context}
故障描述: {query}""")

# ============================================================
#  专家研判建议
# ============================================================
register("expert_advice", "v1", """故障归属不确定,给2条排查建议,简答。故障:{query}""")

register("expert_advice", "v2", """你是SmartHEMS运维专家。故障归属不确定(置信度不足),请给出排查建议。
要求: ①2-3条排查方向 ②每条关联对应Skill或工具 ③说明排除后可判定的方向
故障描述: {query}
已解析字段: {parsed}
路由结果: {dept}(置信度{route_conf})
检索到的相关案例: {retrieved}""")

# ============================================================
#  A/B 测试辅助
# ============================================================
def get_ab_variants(name: str, version_a: str = "v1", version_b: str = "v2"):
    """获取一对 A/B 版本的模板, 用于对比测试"""
    return get(name, version_a), get(name, version_b)

def format_prompt(template_name: str, version: str = None, **kwargs) -> str:
    """获取模板并填充变量"""
    tpl = get(template_name, version)
    return tpl.format(**kwargs)
