"""
0.3 ChromaDB Demo: 把向量存进库、检索最相似的、元数据过滤
承接 embedding_demo: 之前手算相似度, 现在用向量数据库自动化

运行: smartops-agent/.venv/Scripts/python.exe notebooks/chromadb_demo.py
"""
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'  # 国内镜像, 加速模型加载

import chromadb
from chromadb.utils import embedding_functions

# ---- 1. 准备 embedding 函数(BGE, 给 ChromaDB 用)----
# ChromaDB 存/查时会自动调它把文本变向量, 本质和 embedding_demo 里 model.encode 一样
print("加载 BGE embedding 函数(首次慢, 之后走缓存)...")
bge_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name='BAAI/bge-large-zh', device='cuda'
)

# ---- 2. 创建 ChromaDB 客户端 + collection ----
# Client() 内存模式(重启丢失); 真实项目用 PersistentClient(path="chroma_db") 持久化到磁盘
client = chromadb.Client()
collection = client.create_collection(name="fault_cases", embedding_function=bge_ef)
print("已创建 collection: fault_cases\n")

# ---- 3. 存入故障案例(文档 + 元数据, 向量自动算)----
docs = [
    "光伏逆变器输出功率低于设定值,调度策略可能干预",
    "储能电池SOC跳变,BMS通信正常",
    "Modbus通信超时,寄存器无返回",
    "IEC104协议不通,TCP 2404端口异常",
]
metadatas = [
    {"domain": "功率调度", "dept": "控制器部门"},
    {"domain": "储能",     "dept": "储能部门"},
    {"domain": "通信",     "dept": "通信硬件组"},
    {"domain": "电网协议", "dept": "电网协议组"},
]
collection.add(
    documents=docs,
    metadatas=metadatas,
    ids=["case1", "case2", "case3", "case4"]
)
print(f"已存入 {len(docs)} 条故障案例\n")

# ---- 4. 检索1: 给个 query, 找最相似的 Top2 ----
# 注意: ChromaDB 返回的是 distance(距离), 余弦距离 = 1 - 相似度, 越小越像(0=完全相同)
print("=== 检索1: query='逆变器发电量不够' (全库搜 Top2) ===")
res = collection.query(query_texts=["逆变器发电量不够"], n_results=2)
for doc, dist, meta in zip(res['documents'][0], res['distances'][0], res['metadatas'][0]):
    print(f"  [距离 {dist:.3f}] {doc}   | {meta}")

# ---- 5. 检索2: 元数据过滤, 只在"通信"域里搜(架构图的"前置元数据过滤")----
print("\n=== 检索2: query='通信超时' + where domain=通信 ===")
res2 = collection.query(
    query_texts=["通信超时"],
    n_results=2,
    where={"domain": "通信"}
)
for doc, dist, meta in zip(res2['documents'][0], res2['distances'][0], res2['metadatas'][0]):
    print(f"  [距离 {dist:.3f}] {doc}   | {meta}")

print("\n要点:")
print("  1) distance 越小越像(0=完全相同), 和相似度反过来")
print("  2) where 过滤 = 架构图的'按路由域检索', 不全库搜")
print("  3) query 只传文本, 向量由 ChromaDB 自动算")
