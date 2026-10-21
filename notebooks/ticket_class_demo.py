"""Ticket 是类不是函数; '创建即校验' 来自继承的 BaseModel"""
from pydantic import BaseModel
from enum import Enum

# === 普通类: 创建对象, 不校验 ===
class 普通Ticket:
    def __init__(self, title, severity):
        self.title = title
        self.severity = severity

t1 = 普通Ticket(title="功率不符", severity=12345)   # severity 传数字也收
print("【普通类】创建对象, 不校验:")
print(f"  t1.severity = {t1.severity}   (传啥存啥, 12345 也照收)")

# === Pydantic BaseModel 类: 创建对象 + 自动校验 ===
class Severity(str, Enum):
    high = "高"; medium = "中"; low = "低"

class Ticket(BaseModel):      # 关键: 继承 BaseModel
    title: str
    severity: Severity

print("\n【Pydantic BaseModel】创建对象, 自动校验:")
t2 = Ticket(title="功率不符", severity="中")        # 合法
print(f"  Ticket(severity='中') -> 通过, 对象: {t2}")

try:
    Ticket(title="x", severity="紧急")              # 非法
except Exception as e:
    print(f"  Ticket(severity='紧急') -> {type(e).__name__} (创建瞬间就卡住)")

print("""
结论:
  - Ticket 是【类】(class Ticket(BaseModel)), 不是函数
  - Ticket(**dict) 是【创建对象】, 和 Dog('旺财') 一个道理, ** 是解包 dict
  - '创建即校验' 来自继承的 BaseModel; 普通类没这能力, 传啥存啥""")
