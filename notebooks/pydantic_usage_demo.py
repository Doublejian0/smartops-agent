"""Pydantic 用法: 定义 Ticket 后, 到底怎么用?"""
from pydantic import BaseModel
from enum import Enum

class Severity(str, Enum):
    high = "高"; medium = "中"; low = "低"

# ① 定义 schema(就是写个继承 BaseModel 的类, 声明字段类型)
class Ticket(BaseModel):
    title: str
    severity: Severity    # 枚举类型
    dept: str

# ② 创建 + 自动校验: 把 dict 用 ** 解包传进去, Pydantic 逐字段校验
data = {"title": "光伏功率不符", "severity": "中", "dept": "控制器部门"}
ticket = Ticket(**data)    # 等价于 Ticket(title="光伏功率不符", severity="中", dept="控制器部门")
print("✅ 校验通过, 得到对象")

# ③ 通过后, 对象能干嘛:
print("  取字段:", ticket.title, "|", ticket.severity, "|", ticket.dept)
print("  转回dict:", ticket.model_dump())
print("  转JSON:", ticket.model_dump_json(ensure_ascii=False))

# ④ 非法值 -> 抛 ValidationError, except 接住
print("\n非法 severity='紧急':")
try:
    Ticket(title="x", severity="紧急", dept="y")   # "紧急"不是枚举成员
except Exception as e:
    print(f"  ❌ 被卡住: {type(e).__name__}")
    print(f"     (实际项目这里就触发重试, 让LLM重新生成)")
