"""
0.4 LLM 调用 Demo: 调通大模型 API
用 Anthropic SDK 调火山方舟 coding 端点的 glm-5.2(与 Claude Code 同配置)
Anthropic 格式要点: system 单独传, 必须给 max_tokens, 响应取 content[0].text

运行: smartops-agent/.venv/Scripts/python.exe notebooks/llm_demo.py
"""
import os
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()
api_key = os.getenv('ARK_API_KEY')
base_url = os.getenv('ARK_BASE_URL')
model = os.getenv('ARK_MODEL')

print(f"端点: {base_url}")
print(f"模型: {model}\n")

client = Anthropic(api_key=api_key, base_url=base_url)

response = client.messages.create(
    model=model,
    max_tokens=1024,
    system="你是SmartHEMS运维故障诊断助手,回答简洁专业。",
    messages=[
        {"role": "user", "content": "光伏逆变器输出功率低于设定值,可能的原因有哪些?简答3条。"},
    ],
)

print("=== LLM 回答 ===")
for block in response.content:
    if block.type == 'text':
        print(block.text)
    elif block.type == 'thinking':
        print(f"[思考过程]: {block.thinking[:300]}...\n")  # glm-5.2 会先思考再答
print(f"\n(用量: 输入{response.usage.input_tokens} / 输出{response.usage.output_tokens} tokens)")
