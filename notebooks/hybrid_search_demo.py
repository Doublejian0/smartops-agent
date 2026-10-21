"""
0.3 混合检索 Demo: BM25 + 向量 + RRF融合 + Cross-Encoder重排
RAG 核心: 召回(快+全) -> RRF融合 -> 重排(慢+准) 的漏斗

重点观察: doc3(寄存器40001) vs doc4(寄存器40002)
  - 向量分不清(语义太像)
  - BM25 精确区分(关键词40001命中doc3)
  - 融合+重排后, doc3 应排前

运行: smartops-agent/.venv/Scripts/python.exe notebooks/hybrid_search_demo.py
"""
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'  # 国内镜像

import numpy as np
from sentence_transformers import SentenceTransformer, CrossEncoder
import jieba
from rank_bm25 import BM25Okapi

# ---- 文档库 + 查询 ----
docs = [
    "光伏逆变器输出功率低于设定值,调度策略可能干预",   # 0
    "逆变器出力不足,发电量偏低",                       # 1
    "储能电池SOC跳变,BMS通信正常",                    # 2
    "Modbus通信超时,寄存器40001无返回",               # 3  ← query精确命中
    "Modbus通信超时,寄存器40002无返回",               # 4  ← 和doc3只差一个数字
    "IEC104协议不通,TCP 2404端口异常",               # 5
]
query = "Modbus寄存器40001超时"

# ==== 1. BM25 召回(关键词检索, 精确字面匹配)====
# 中文要先分词: jieba 把句子切成词
tokenized_docs = [list(jieba.cut(d)) for d in docs]
bm25 = BM25Okapi(tokenized_docs)
bm25_scores = bm25.get_scores(list(jieba.cut(query)))
bm25_rank = np.argsort(bm25_scores)[::-1]  # 按分数降序得排名
print("【BM25 召回】(精确关键词, 能区分40001/40002):")
for i in bm25_rank[:5]:
    print(f"   得分{bm25_scores[i]:.2f}  doc{i}: {docs[i]}")

# ==== 2. 向量 召回(语义检索, 懂意思但可能分不清40001/40002)====
model = SentenceTransformer('BAAI/bge-large-zh', device='cuda')
doc_embs = model.encode(docs, normalize_embeddings=True)
query_emb = model.encode([query], normalize_embeddings=True)[0]
vec_sims = doc_embs @ query_emb  # 归一化后点积 = 余弦相似度
vec_rank = np.argsort(vec_sims)[::-1]
print("\n【向量 召回】(语义, 可能分不清40001/40002):")
for i in vec_rank[:5]:
    print(f"   相似{vec_sims[i]:.3f}  doc{i}: {docs[i]}")

# ==== 3. RRF 融合(按排名融合, 不看分数看排名)====
def rrf_fuse(ranks, k=60):
    """ranks: 多路排名列表; 每个文档得分 = Σ 1/(k+排名位次)"""
    scores = {}
    for rank in ranks:
        for pos, doc_id in enumerate(rank):
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + pos)
    fused = sorted(scores, key=scores.get, reverse=True)
    return fused, scores
fused, fused_scores = rrf_fuse([bm25_rank, vec_rank])
print("\n【RRF 融合】(两路按排名合并, 不用管分数量纲):")
for i in fused[:5]:
    print(f"   融合分{fused_scores[i]:.4f}  doc{i}: {docs[i]}")

# ==== 4. Cross-Encoder 重排(对融合Top5精排)====
# 与向量(双塔)区别: query+doc拼一起送模型, 内部交互, 准但慢
print("\n加载 bge-reranker-large (首次下载~1.3G, 请耐心)...")
reranker = CrossEncoder('BAAI/bge-reranker-large', device='cuda')
candidates = fused[:5]
pairs = [(query, docs[i]) for i in candidates]
rerank_scores = reranker.predict(pairs)
final_order = np.argsort(rerank_scores)[::-1]
print("\n【Cross-Encoder 重排】(最终结果):")
for idx in final_order:
    i = candidates[idx]
    print(f"   重排分{float(rerank_scores[idx]):.3f}  doc{i}: {docs[i]}")

print("\n漏斗总结: BM25+向量(快全, Top5) -> RRF融合 -> Cross-Encoder(慢准, 最终排序)")
print("关键: 看 doc3(40001) 是否在重排后排第一")
