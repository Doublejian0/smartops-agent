"""rag/retrieval.py - 检索管线 V2（多查询 + 同义词 + BM25/向量 + RRF）"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np
import jieba
from rank_bm25 import BM25Okapi

from src.core.synonym_dict import normalize
from src.core.llm import get_llm, get_text


async def multi_query(query, n=3):
    """构造 n 个查询变体：原查询 + LLM 扩写，失败则平滑回退。"""
    query = normalize(query)
    variants = [query]

    try:
        llm = get_llm()
        prompt = (
            "SmartHEMS 运维检索：将下列故障描述改写为 3 个可用于检索的查询语句，\n"
            "每行一个，不要编号，逗号分隔词可保留：\n"
            f"{query}"
        )
        resp = await llm.ainvoke(prompt)
        text = get_text(resp)
        for q in text.splitlines():
            q = q.strip("\t -••")
            if not q:
                continue
            if q not in variants:
                variants.append(q)
            if len(variants) >= n + 1:
                break
    except Exception:
        # 回退策略：无 LLM 也能运行
        pass

    while len(variants) < n + 1:
        variants.append(query)

    return variants[: n + 1]


def rrf(ranks, k=60):
    """RRF 融合: 按排名 1/(k+rank)"""
    s = {}
    for rank in ranks:
        for pos, did in enumerate(rank):
            s[did] = s.get(did, 0) + 1 / (k + pos)
    fused = sorted(s.keys(), key=lambda did: s[did], reverse=True)
    return fused, s


def _safe_doc_text(all_ids, all_docs, didx):
    """从 position 映射到文档文本。"""
    try:
        didx_int = int(didx)
        if 0 <= didx_int < len(all_docs):
            return all_ids[didx_int], all_docs[didx_int]
    except Exception:
        pass
    return str(didx), ""


def _index_top_ids(scores, all_ids, top_k):
    """将 BM25 的分数索引转为文档ID列表。"""
    top_idx = np.argsort(scores)[::-1][:top_k]
    ids = []
    for i in top_idx:
        try:
            i = int(i)
            if i < len(all_ids):
                ids.append(str(all_ids[i]))
        except Exception:
            continue
    return ids


def _vec_search_all(queries, collection, where, top_k):
    """向量检索整路：对每个查询变体跑一次向量检索，返回排名列表。"""
    ranks = []
    for q in queries:
        try:
            res = collection.query(query_texts=[q], n_results=top_k, where=where)
            if res and res.get("ids"):
                ranks.append([str(x) for x in res["ids"][0]])
        except Exception:
            pass
    return ranks


def _bm25_search_all(queries, bm25, all_ids, top_k):
    """BM25 检索整路：对每个查询变体跑一次关键词检索，返回排名列表。"""
    if bm25 is None:
        return []
    ranks = []
    for q in queries:
        try:
            scores = bm25.get_scores(list(jieba.cut(q or "")))
            ranks.append(_index_top_ids(scores, all_ids, top_k=top_k))
        except Exception:
            continue
    return ranks


async def retrieve(query, collection, domain: Optional[str] = None, top_k: int = 5):
    """
    检索: 同义词标准化 -> 可选元数据过滤 -> 向量/关键词双路 -> RRF融合
    返回 [(doc_id, doc_text, score)]。

    双路并行: 向量检索与 BM25 检索互不依赖, 用线程池并行执行。
    (CPU 密集 + numpy 底层释放 GIL, 多线程比 asyncio 更适合这里。)
    """
    query = normalize(query)
    where = {"domain": domain} if domain else None

    all_docs = collection.get()["documents"] if hasattr(collection, "get") else []
    all_ids = collection.get()["ids"] if hasattr(collection, "get") else []
    id_to_doc = {str(did): doc for did, doc in zip(all_ids, all_docs)}

    queries = await multi_query(query)

    bm25 = BM25Okapi([list(jieba.cut(d or "")) for d in all_docs]) if all_docs else None

    # 双路并行：向量 + BM25 互不依赖，提交到线程池同时执行
    with ThreadPoolExecutor(max_workers=2) as ex:
        vec_future = ex.submit(_vec_search_all, queries, collection, where, top_k)
        bm25_future = ex.submit(_bm25_search_all, queries, bm25, all_ids, top_k)
        vec_ranks = vec_future.result()
        bm25_ranks = bm25_future.result()

    # 若都没拿到，回退: 用同义词标准化后的前 top_k 文档
    if not vec_ranks and not bm25_ranks:
        fallback_ids = [str(d) for d in all_ids[:top_k]]
        return [(did, id_to_doc.get(did, ''), 0.0) for did in fallback_ids]

    fused, scores = rrf(vec_ranks + bm25_ranks)
    return [(did, id_to_doc.get(did, ''), scores.get(did, 0.0)) for did in fused[:top_k]]
