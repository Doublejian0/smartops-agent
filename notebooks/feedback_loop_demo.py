"""
V1-6 反馈回写: 人工修正实时入库(架构图3.4+9)
系统判错 -> 人工修正 dept/根因 -> 实时 add 到知识库 -> 下次检索受益

运行: HF_HUB_OFFLINE=1 smartops-agent/.venv/Scripts/python.exe notebooks/feedback_loop_demo.py
"""
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
from chromadb.utils import embedding_functions
import chromadb

bge_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name='BAAI/bge-large-zh', device='cuda')
client = chromadb.Client()
try: client.delete_collection("feedback_kb")
except: pass
kb = client.create_collection("feedback_kb", embedding_function=bge_ef)
kb.add(documents=["光伏功率不符,调度策略干预"], metadatas=[{"dept": "控制器部门", "id": "c0"}], ids=["c0"])

# === 反馈回写: 人工修正后, 实时新增案例入库 ===
def feedback_write(query, corrected_dept, corrected_root_cause):
    new_id = f"fb{len(kb.get()['ids'])}"
    new_doc = f"{query},根因:{corrected_root_cause}"
    kb.add(documents=[new_doc], metadatas=[{"dept": corrected_dept, "id": new_id}], ids=[new_id])
    print(f"  [反馈回写] 新增案例入库: 「{new_doc}」| dept={corrected_dept}")

# === 场景: 系统判错, 人工修正 ===
print("=== 1. 系统原始判断(可能错)===")
print("  系统判: 控制器部门(疑似错, 实际是逆变器问题)")

print("\n=== 2. 人工修正 -> 实时回写知识库 ===")
print("  人工修正: dept=逆变器硬件组, 根因=IGBT过温触发降额")
feedback_write("光伏逆变器输出功率低", "逆变器硬件组", "IGBT过温触发降额")

print("\n=== 3. 验证: 下次相似问题, 检索到修正后的案例 ===")
res = kb.query(query_texts=["逆变器功率不够"], n_results=2)
for doc, meta in zip(res['documents'][0], res['metadatas'][0]):
    print(f"  [{meta['dept']}] {doc}")

print("\n✅ 反馈回写: 人工修正实时入库, 知识库自学习越用越准")
print("   (架构图: 不等关单, 修正即回流; 下次RAG投票/检索就能用上新案例)")
