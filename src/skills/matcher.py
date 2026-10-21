"""skills/matcher.py - Skill匹配(关键词+domain加权)"""
from src.skills.templates import SKILLS

def skill_match(query, domain=None):
    """返回 (最佳Skill, 匹配分)"""
    best, best_score = None, 0
    for skill in SKILLS:
        score = sum(1 for k in skill["keywords"] if k in query)
        if domain and skill["domain"] == domain:
            score += 2   # domain匹配加权
        if score > best_score:
            best, best_score = skill, score
    return best, best_score
