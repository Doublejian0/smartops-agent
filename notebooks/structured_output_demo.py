"""
0.4 结构化输出 Demo: 让 LLM 按 schema 输出工单 JSON + Pydantic 校验
对应架构图: 工单生成 Agent(结构化输出 + 字段校验)

运行: smartops-agent/.venv/Scripts/python.exe notebooks/structured_output_demo.py
"""
import os, json, re
from dotenv import load_dotenv
from anthropic import Anthropic
from pydantic import BaseModel, field_validator
from typing import List
from enum import Enum

load_dotenv()
client = Anthropic(api_key=os.getenv('ARK_API_KEY'), base_url=os.getenv('ARK_BASE_URL'))
model = os.getenv('ARK_MODEL')

# ---- 1. Pydantic 定义工单 schema(字段 + 类型 + 校验规则)----
class Severity(str, Enum):
    high = "高"; medium = "中"; low = "低"

DEPTS = ["控制器部门", "逆变器硬件组", "储能部门", "通信硬件组", "电网协议组", "充电桩组", "电网侧(非本部门)"]

class Ticket(BaseModel):
    title: str
    product_version: str
    severity: Severity                    # 枚举: 必须是 高/中/低
    description: str
    preliminary_analysis: str
    suggested_dept: str
    related_cases: List[str] = []

    @field_validator('suggested_dept')     # 自定义校验: dept 必须在预设列表
    @classmethod
    def check_dept(cls, v):
        if v not in DEPTS:
            raise ValueError(f'suggested_dept 必须是 {DEPTS} 之一, 你给的是 {v}')
        return v

# ---- 2. Prompt: 要求 LLM 输出工单 JSON ----
fault_desc = "客户设置光伏输出功率15kW,实测仅10kW。Modbus寄存器40001读值正常(15kW),但实际输出不符。已排除电网上限、储能SOC限值。"

prompt = f"""你是SmartHEMS运维工单生成助手。根据故障描述生成结构化工单,严格输出JSON(不要输出其他内容,不要markdown代码块)。

故障描述:{fault_desc}

JSON字段说明:
- title: 工单标题,格式"[部门] 简述(设置值/实际值)"
- product_version: 产品版本,如SmartHEMS V3.2.1
- severity: 严重程度,必须是"高"/"中"/"低"之一
- description: 故障详细描述
- preliminary_analysis: 初步分析(疑似根因)
- suggested_dept: 建议归属部门,必须是{DEPTS}之一
- related_cases: 相似案例ID列表,无则空数组

只输出JSON对象:"""

# ---- 3. 调 LLM ----
response = client.messages.create(
    model=model, max_tokens=2048,
    messages=[{"role": "user", "content": prompt}]
)
# glm-5.2 可能有 thinking, 取 text 块
text = next((b.text for b in response.content if b.type == 'text'), '')
print("=== LLM 原始输出(text块) ===")
print(text)

# ---- 4. 从文本提取 JSON(LLM 可能带额外文字/markdown) ----
match = re.search(r'\{.*\}', text, re.DOTALL)
if not match:
    print("\n❌ 未找到 JSON!"); exit()
ticket_json = json.loads(match.group())
print("\n=== 解析出的 JSON ===")
print(json.dumps(ticket_json, ensure_ascii=False, indent=2))

# ---- 5. Pydantic 校验 ----
print("\n=== Pydantic 校验 ===")
try:
    ticket = Ticket(**ticket_json)
    print("✅ 校验通过! 工单对象:")
    print(ticket.model_dump_json(indent=2, ensure_ascii=False))
except Exception as e:
    print(f"❌ 校验失败: {e}")
    print("(实际项目这里会重试让LLM重新生成, 最多2次)")
