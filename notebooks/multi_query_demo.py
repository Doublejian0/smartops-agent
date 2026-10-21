"""
0.4 多查询生成 Demo: 用LLM把query扩写成3个语义变体, 提升RAG召回
用 langchain ChatAnthropic 封装LLM(对比之前裸写 anthropic SDK, 更简洁)
对应架构图4.3: 多查询生成(标准化/根因向/细节向)

运行: smartops-agent/.venv/Scripts/python.exe notebooks/multi_query_demo.py
"""
import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()

# === LangChain 封装 LLM(对比之前裸写 anthropic SDK, 一行搞定)===
llm = ChatAnthropic(
    api_key=os.getenv('ARK_API_KEY'),
    base_url=os.getenv('ARK_BASE_URL'),
    model=os.getenv('ARK_MODEL'),
    max_tokens=1024,
)

query = "功率不对"

# Prompt: 扩写成3个不同角度的检索变体(架构图4.3)
# 关键: 必须给领域上下文, 否则LLM会跑偏(把"功率"理解成服务器电源而非光伏调度)
prompt = f"""你是SmartHEMS(光伏+储能+充电桩智能能源管理系统)运维检索助手。这里的"功率"指光伏输出功率/调度功率,不是服务器电源。
把下面的用户口语问题,扩写成3个不同角度的检索查询,用于提升知识库召回率:
1. 标准化: 用规范术语重述问题
2. 根因向: 针对可能的根本原因
3. 细节向: 针对具体技术细节/模块

用户问题: {query}

只输出3行查询, 每行一个, 不要编号不要解释:"""

# === LangChain 调用: invoke(对比之前 client.messages.create)===
resp = llm.invoke(prompt)

# glm-5.2 可能返回 thinking + text, content 可能是 str 或 blocks 列表
content = resp.content
if isinstance(content, list):
    text = ''.join(b.get('text', '') if isinstance(b, dict) else getattr(b, 'text', '')
                   for b in content
                   if (b.get('type') if isinstance(b, dict) else getattr(b, 'type', '')) == 'text')
else:
    text = content

print(f"原始query: 「{query}」(太口语, 直接检索召回率低)\n")
print("=== LLM 扩写的3个查询变体 ===")
print(text)

print("\n要点: 3个变体从不同角度, 各自检索后合并去重, 大幅提升口语化问题的召回率")
print("(下一步完整RAG: 用这3个变体检索ChromaDB, 合并结果, 喂给LLM生成带来源的答案)")
