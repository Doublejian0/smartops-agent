"""agents/ticket_gen.py - 工单Agent(结构化输出 + Pydantic 校验 + 失败重试)"""
import json
import re
from enum import Enum
from typing import List

from pydantic import BaseModel, Field, ValidationError, field_validator

from src.core.config import DEPTS
from src.core.llm import get_llm, get_text


class Severity(str, Enum):
    high = "高"
    medium = "中"
    low = "低"


class Ticket(BaseModel):
    title: str
    product_version: str
    severity: Severity
    description: str
    preliminary_analysis: str
    suggested_dept: str
    related_cases: List[str] = Field(default_factory=list)

    @field_validator("suggested_dept")
    @classmethod
    def check_dept(cls, v):
        if v not in DEPTS:
            raise ValueError(f"suggested_dept 必须在 {DEPTS}")
        return v

    @field_validator("related_cases", mode="before")
    @classmethod
    def coerce_related_cases(cls, v):
        """宽容转换: LLM 常把 related_cases 输出成索引整数[0,1,2]或检索片段dict,
        统一转成字符串, 避免因格式问题整单校验失败。"""
        if not isinstance(v, list):
            return v
        out = []
        for item in v:
            if isinstance(item, dict):
                out.append(f"{item.get('id', '')}: {str(item.get('description', ''))[:50]}")
            else:
                out.append(str(item))
        return out


def _safe_load_json(text: str):
    """从模型文本里提取首个 JSON，失败则返回空 dict。"""
    if not text:
        return {}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return {}


# Function Calling 工具定义：让 LLM 通过工具调用输出结构化工单（比 JSON 文本+正则抠可靠）
TICKET_TOOL = {
    "type": "function",
    "function": {
        "name": "create_ticket",
        "description": "根据故障描述和知识库生成运维工单",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "工单标题"},
                "product_version": {"type": "string", "description": "产品版本"},
                "severity": {"type": "string", "enum": ["高", "中", "低"], "description": "严重程度"},
                "description": {"type": "string", "description": "故障现象描述"},
                "preliminary_analysis": {"type": "string", "description": "初步原因分析"},
                "suggested_dept": {"type": "string", "description": "归属部门"},
                "related_cases": {"type": "array", "items": {"type": "string"}, "description": "相关案例ID列表"},
            },
            "required": ["title", "product_version", "severity", "description", "preliminary_analysis", "suggested_dept"],
        },
    },
}


async def gen_ticket(query, dept, retrieved=None, max_retry=2):
    """基于检索结果生成工单：Function Calling 强制结构化输出 + Pydantic 校验。"""
    llm = get_llm()
    context = "\n".join(f"[{i}] {d}" for i, (d, _, _) in enumerate(retrieved or [])) or "无"
    prompt = (
        f"根据故障和知识库生成运维工单。\n"
        f"归属部门:{dept}\n"
        f"知识库:\n{context}\n故障:{query}"
    )

    # 强制 LLM 调用 create_ticket 工具（结构化输出，比 JSON 文本+正则抠可靠）
    tool_choice = {"type": "function", "function": {"name": "create_ticket"}}

    for _ in range(max_retry + 1):
        rsp = await llm.ainvoke_with_tools(prompt, [TICKET_TOOL], tool_choice=tool_choice)
        message = rsp.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            print("  [工单解析失败重试] 模型未返回工具调用")
            continue

        try:
            # OpenAI 格式：arguments 是 JSON 字符串
            args = json.loads(tool_calls[0].function.arguments)
            return Ticket(**args)
        except (ValidationError, json.JSONDecodeError) as e:
            print(f"  [工单校验失败重试] {e}")

    # 重试耗尽兜底: 也返回 Ticket 对象(保持类型契约, 编排图不崩)
    return Ticket(
        title="",
        product_version="SmartHEMS V3.2.1",
        severity="中",
        description="",
        preliminary_analysis="",
        suggested_dept=dept if dept in DEPTS else "不确定",
        related_cases=[],
    )
