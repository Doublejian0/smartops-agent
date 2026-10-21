"""Pydantic 校验原理演示: 看它怎么"卡住"非法值"""
from pydantic import BaseModel, field_validator
from enum import Enum

class Severity(str, Enum):
    high = "高"; medium = "中"; low = "低"

DEPTS = ["控制器部门", "逆变器硬件组", "储能部门"]

class Ticket(BaseModel):
    severity: Severity                   # ① 类型声明: 必须是枚举成员, 自动卡
    suggested_dept: str
    @field_validator('suggested_dept')   # ② 自定义校验: dept 必须在 DEPTS
    @classmethod
    def check_dept(cls, v):
        if v not in DEPTS:
            raise ValueError(f'"{v}" 不在允许的部门列表 {DEPTS}')
        return v

print("=== 1. 合法值(应该通过)===")
t = Ticket(severity="中", suggested_dept="控制器部门")
print("✅ 通过:", t)

print("\n=== 2. 非法 severity='紧急'(枚举自动卡)===")
try:
    Ticket(severity="紧急", suggested_dept="控制器部门")
except Exception as e:
    print(f"❌ 被卡住! 异常类型: {type(e).__name__}")
    print(f"   报错: {e}")

print("\n=== 3. 非法 dept='其他部门'(field_validator 卡)===")
try:
    Ticket(severity="中", suggested_dept="其他部门")
except Exception as e:
    print(f"❌ 被卡住! 异常类型: {type(e).__name__}")
    print(f"   报错: {e}")
