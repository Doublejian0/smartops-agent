"""rag/embedding.py - BGE embedding + ChromaDB collection 管理"""
import chromadb
from chromadb.utils import embedding_functions
from src.core.config import EMBEDDING_MODEL, EMBEDDING_DEVICE, CHROMA_PATH

_ef = None
def get_embedding_function():
    """单例 BGE embedding 函数"""
    global _ef
    if _ef is None:
        _ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL, device=EMBEDDING_DEVICE)
    return _ef

def get_client():
    """ChromaDB 客户端(有路径则持久化, 无则内存)"""
    return chromadb.PersistentClient(path=CHROMA_PATH) if CHROMA_PATH else chromadb.Client()

def get_or_create_collection(name, domain_docs=None):
    """获取/创建 collection; 传入 domain_docs=[(doc, metadata),...] 可初始化"""
    client = get_client()
    try: client.delete_collection(name)
    except: pass
    col = client.create_collection(name, embedding_function=get_embedding_function())
    if domain_docs:
        docs = [d for d, _ in domain_docs]
        metas = [m for _, m in domain_docs]
        col.add(documents=docs, metadatas=metas, ids=[f"{name}_{i}" for i in range(len(docs))])
    return col
