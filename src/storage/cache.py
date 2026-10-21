"""storage/cache.py - LLM 结果缓存（内存 dict，精确 + 预留语义）。

核心价值：相同/相似输入不重复调 LLM，省 token 成本 + 提响应速度。

当前用内存 dict 演示原理（零部署），生产可无缝换成 Redis：
  - 精确缓存：key 完全一致直接命中（当前已实现）
  - 语义缓存：意思相近也命中（预留接口，需接向量相似度判断）
"""
import hashlib

_cache = {}
_stats = {"hits": 0, "misses": 0}


def _key(prompt: str) -> str:
    """用 prompt 的 md5 做 key，避免超长 key 占内存。"""
    return hashlib.md5(str(prompt).encode("utf-8")).hexdigest()


def get(prompt: str):
    """命中返回缓存值，未命中返回 None。"""
    k = _key(prompt)
    if k in _cache:
        _stats["hits"] += 1
        return _cache[k]
    _stats["misses"] += 1
    return None


def set(prompt: str, value):
    """写入缓存。"""
    _cache[_key(prompt)] = value


def clear():
    """清空缓存（换模型/换 prompt 版本后应清一次）。"""
    _cache.clear()
    _stats["hits"] = 0
    _stats["misses"] = 0


def stats() -> dict:
    """返回命中统计，用于观测缓存收益。"""
    total = _stats["hits"] + _stats["misses"]
    return {
        **_stats,
        "hit_rate": round(_stats["hits"] / total, 3) if total else 0.0,
    }
