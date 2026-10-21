"""storage/db.py - 传统库（SQLite）存诊断记录与反馈，作为数据真相源。

上线后向量库（ChromaDB）只做语义检索索引，可随时从本库重建；
本库是业务数据的"正本"，负责精确查询、统计、审计。
SQLite 零部署，本地可直接跑；生产换 MySQL 只改这一层，不动上层。
"""
import json
import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smartops.db")


def get_conn():
    """获取连接，row_factory 让查询结果能按列名取值。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """建表（幂等）。诊断记录 + 反馈记录两张核心表。"""
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS diagnoses (
            diagnosis_id   TEXT PRIMARY KEY,
            query          TEXT,
            parsed         TEXT,
            dept           TEXT,
            route_conf     REAL,
            search_score   REAL,
            confidence     REAL,
            branch         TEXT,
            result         TEXT,
            status         TEXT,
            created_at     TEXT
        );
        CREATE TABLE IF NOT EXISTS feedbacks (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            diagnosis_id   TEXT,
            corrected_dept TEXT,
            root_cause     TEXT,
            created_at     TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def save_diagnosis(record: dict):
    """写入一条诊断记录。record 键对应 diagnoses 表字段。"""
    init_db()
    conn = get_conn()
    conn.execute(
        """
        INSERT OR REPLACE INTO diagnoses
        (diagnosis_id, query, parsed, dept, route_conf, search_score,
         confidence, branch, result, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.get("diagnosis_id", ""),
            record.get("query", ""),
            json.dumps(record.get("parsed", {}), ensure_ascii=False),
            record.get("dept", ""),
            record.get("route_conf", 0.0),
            record.get("search_score", 0.0),
            record.get("confidence", 0.0),
            record.get("branch", ""),
            record.get("result", ""),
            record.get("status", "done"),
            record.get("created_at", datetime.now().isoformat()),
        ),
    )
    conn.commit()
    conn.close()


def save_feedback(record: dict):
    """写入一条人工反馈（审计留痕：谁在何时改了什么）。"""
    init_db()
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO feedbacks (diagnosis_id, corrected_dept, root_cause, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            record.get("diagnosis_id", ""),
            record.get("corrected_dept", ""),
            record.get("root_cause", ""),
            record.get("created_at", datetime.now().isoformat()),
        ),
    )
    conn.commit()
    conn.close()


def query_diagnoses(dept: str = None, limit: int = 50):
    """查询诊断记录（可按部门过滤），供统计/追溯。"""
    init_db()
    conn = get_conn()
    if dept:
        rows = conn.execute(
            "SELECT * FROM diagnoses WHERE dept = ? ORDER BY created_at DESC LIMIT ?",
            (dept, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM diagnoses ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
