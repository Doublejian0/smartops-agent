"""core/synonym_dict.py - 同义词表加载 + 替换（供检索管线调用）"""
import os
import re
import yaml

_synonym_map = None  # {alias: standard_word}
_compiled_pattern = None

def _load():
    """延迟加载同义词表"""
    global _synonym_map, _compiled_pattern
    if _synonym_map is not None:
        return
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "synonym_dict.yaml")
    with open(path, encoding='utf-8') as f:
        raw = yaml.safe_load(f)
    _synonym_map = {}
    for _standard, entry in raw.items():
        _synonym_map[entry["standard"]] = entry["standard"]  # 自身映射
        for alias in entry.get("aliases", []):
            _synonym_map[alias] = entry["standard"]
    # 编译正则: 按 alias 长度降序(长词优先替换)
    aliases_sorted = sorted(_synonym_map.keys(), key=len, reverse=True)
    _compiled_pattern = re.compile('|'.join(re.escape(a) for a in aliases_sorted if a))

def normalize(text: str) -> str:
    """将文本中的口语词替换为标准术语, 返回标准化文本"""
    _load()
    if not _compiled_pattern:
        return text

    def _replace(m):
        return _synonym_map.get(m.group(), m.group())
    return _compiled_pattern.sub(_replace, text)

def get_standard(word: str) -> str:
    """查询单个词的标准形式"""
    _load()
    return _synonym_map.get(word, word)

def get_all_terms() -> dict:
    """返回完整映射表 {标准词: [别名列表]}"""
    _load()
    result = {}
    for alias, std in _synonym_map.items():
        if alias != std:
            result.setdefault(std, []).append(alias)
    return result
