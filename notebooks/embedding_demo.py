"""
0.3 第一个 Embedding Demo
目标:亲手验证 "文本 -> 向量 -> 语义相似度"
     看到意思相近的句子,余弦相似度真的更高

运行: smartops-agent/.venv/Scripts/python.exe notebooks/embedding_demo.py
"""
import os
import torch
import numpy as np

# 【坑】HuggingFace 在国内访问慢/不稳,设这个环境变量走国内镜像 hf-mirror
# 必须在 import sentence_transformers 之前设置才生效
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

from sentence_transformers import SentenceTransformer

# ---- 1. 加载 BGE-large-zh 模型 ----
# 首次运行会从镜像下载模型(~1.3G),之后走本地缓存,秒加载
device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f"正在加载 BGE-large-zh 到 {device} ...(首次需下载,请耐心)")
model = SentenceTransformer('BAAI/bge-large-zh', device=device)
print("模型加载完成!\n")

# ---- 2. 准备几句话(运维场景)----
sentences = [
    "光伏逆变器输出功率低于设定值",     # 语义A:功率不足
    "逆变器出力不足,发电量偏低",         # 语义A:同义、不同字
    "储能电池SOC校准出现偏差",          # 语义B:储能问题
    "今天天气真不错,适合出去玩",        # 无关
]

# ---- 3. 文本 -> 向量 ----
# encode 批量转换,返回 numpy 数组,形状 [句子数, 维度]
# BGE-large-zh 输出 1024 维
embeddings = model.encode(sentences, normalize_embeddings=False)
print(f"句向量形状: {embeddings.shape}  -> {len(sentences)} 句话 × {embeddings.shape[1]} 维向量\n")

# ---- 4. 算两两余弦相似度 ----
# 余弦相似度 = (a·b) / (|a| × |b|),范围 [-1, 1],越接近 1 越相似
def cosine_similarity(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

print("两两余弦相似度(越接近 1 = 语义越相近):\n")
for i in range(len(sentences)):
    for j in range(i + 1, len(sentences)):
        sim = cosine_similarity(embeddings[i], embeddings[j])
        print(f"  {sim:.3f}   「{sentences[i]}」<-->「{sentences[j]}」")

print("\n预期:前两句(都是功率不足)相似度最高;和'天气'那句最低。")
