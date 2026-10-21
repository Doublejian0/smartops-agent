"""core/llm.py - LLM 封装(单例, 所有 Agent 复用)"""
import asyncio

from openai import AsyncOpenAI

from src.core.config import ARK_API_KEY, ARK_BASE_URL, ARK_MODEL, LLM_MAX_TOKENS
from src.storage import cache


class _DeepSeekResponse:
    """最小兼容对象：仅提供与现有代码约定一致的 content 字段。"""

    def __init__(self, content: str):
        self.content = content


class _OpenAICompatLLM:
    """轻量 OpenAI 风格异步客户端包装，暴露 ainvoke(prompt) 主入口。

    异步为主：ainvoke 用 AsyncOpenAI 的非阻塞调用，等待 LLM 时释放事件循环线程。
    同步兼容：invoke 内部用 asyncio.run 包一层，供命令行/评估脚本等同步场景使用。
    """

    def __init__(self, api_key: str, base_url: str, model: str, max_tokens: int):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._max_tokens = max_tokens

    def _extract(self, rsp) -> str:
        """从 OpenAI 响应里取文本。"""
        content = ""
        if rsp and getattr(rsp, "choices", None):
            choice0 = rsp.choices[0]
            message = getattr(choice0, "message", None)
            content = getattr(message, "content", "") or ""
        return content

    async def ainvoke(self, prompt):
        """异步调用：带缓存。命中缓存直接返回，未命中调 LLM 后写缓存。"""
        cached = cache.get(prompt)
        if cached is not None:
            return cached

        rsp = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": str(prompt)}],
            max_tokens=self._max_tokens,
        )
        result = _DeepSeekResponse(self._extract(rsp))
        cache.set(prompt, result)
        return result

    async def ainvoke_with_tools(self, prompt, tools, tool_choice=None):
        """Function Calling：带工具定义调用，LLM 可能返回 tool_calls。

        tools: OpenAI 格式工具定义列表（name + description + parameters）
        tool_choice: None(自动) 或 {"type":"function","function":{"name":"xxx"}}(强制调用)
        返回完整响应，由调用方处理 message.tool_calls。
        """
        kwargs = {
            "model": self._model,
            "messages": [{"role": "user", "content": str(prompt)}],
            "tools": tools,
            "max_tokens": self._max_tokens,
        }
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        return await self._client.chat.completions.create(**kwargs)

    def invoke(self, prompt):
        """同步兼容入口：内部跑事件循环，等待异步版本完成。"""
        return asyncio.run(self.ainvoke(prompt))


_llm = None


def _get_ark_key() -> str:
    """返回 API Key，若缺失抛可读异常。"""
    if not ARK_API_KEY:
        raise RuntimeError(
            "ARK_API_KEY 未配置：请在 smartops-agent/.env 中设置 ARK_API_KEY="
            "(与 CLAUDE_CODE 同一套配置)。"
        )
    return ARK_API_KEY.strip()


def get_llm():
    """单例 LLM(异步客户端), 避免重复初始化"""
    global _llm
    if _llm is None:
        _llm = _OpenAICompatLLM(
            api_key=_get_ark_key(),
            base_url=ARK_BASE_URL,
            model=ARK_MODEL,
            max_tokens=LLM_MAX_TOKENS,
        )
    return _llm


def get_text(resp):
    """从 LLM 响应取文本(兼容字符串与块结构)。"""
    content = getattr(resp, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, (list, tuple)):
        texts = []
        for block in content:
            if isinstance(block, str):
                texts.append(block)
                continue

            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                else:
                    texts.append(block.get("text", "") or "")
                continue

            # 某些版本对象可能带 text 属性
            texts.append(getattr(block, "text", "") or "")

        return "".join(texts)

    return ""

