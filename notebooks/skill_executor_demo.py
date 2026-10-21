"""
V1-4 Skill继续: 子工作流(步骤自动调工具执行, 不再静态清单)
升级: Skill步骤里的 knowledge_search 真能调, Agent按步骤执行排查

运行: HF_HUB_OFFLINE=1 smartops-agent/.venv/Scripts/python.exe notebooks/skill_executor_demo.py
"""
import os, re
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
from chromadb.utils import embedding_functions
import chromadb

# 精简Skill(功率不符排查, 步骤关联knowledge_search工具)
SKILL = {
    "name": "功率不符排查",
    "steps": [
        "查参数配置(-> knowledge_search('功率上限参数'))",
        "查调度策略(-> knowledge_search('调度策略 功率分配'))",
        "查限电保护(-> knowledge_search('限电保护'))",
    ]
}

# 建知识库(供 knowledge_search 工具检索)
bge_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name='BAAI/bge-large-zh', device='cuda')
client = chromadb.Client()
try: client.delete_collection("skill_kb")
except: pass
kb = client.create_collection("skill_kb", embedding_function=bge_ef)
kb.add(documents=["功率上限参数:dispatch_power限值可配", "调度策略:功率分配按优先级", "限电保护:电网指令触发"],
       metadatas=[{"id": f"d{i}"} for i in range(3)], ids=[f"d{i}" for i in range(3)])

# === knowledge_search 工具(检索知识库)===
def knowledge_search(query, top_k=2):
    res = kb.query(query_texts=[query], n_results=top_k)
    return res['documents'][0]

# === 子工作流: 按步骤执行, 遇 knowledge_search 就调工具 ===
def execute_skill(skill):
    print(f"执行Skill: {skill['name']}\n")
    for i, step in enumerate(skill['steps'], 1):
        print(f"步骤{i}: {step}")
        # 解析步骤里的 knowledge_search('xxx') 调用
        m = re.search(r"knowledge_search\('([^']+)'\)", step)
        if m:
            q = m.group(1)
            print(f"  -> 调用 knowledge_search('{q}'):")
            for r in knowledge_search(q):
                print(f"     • {r}")
        print()

execute_skill(SKILL)
print("✅ Skill子工作流: 步骤自动调工具执行(从静态清单升级为可执行)")
print("   (后续可加 register_check/log_analyzer 工具, 让更多步骤可执行)")
