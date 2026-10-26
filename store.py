"""待办数据层（SQLite）。

Web 路由（main.py）与 MCP server（mcp_server.py）共用这一份实现，
避免"两处 SQL 各写一遍、改一处忘一处"。
"""

import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 建表语句（todos：id / name / completed）
CREATE_SQL = """
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0
)
"""

# 种子数据：表为空时插入这些记录（name, completed）
SEEDS = [("学 Express", 1), ("接前端", 0), ("学 Python + FastAPI", 0)]


def db_path() -> Path:
    """调用时读环境变量 —— 测试可以用 TODO_DB 指向临时库。"""
    return Path(os.getenv("TODO_DB", str(BASE_DIR / "todos.db")))


def _connect():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """建表；只在空表时插种子，重复调用无副作用。"""
    conn = _connect()
    try:
        conn.execute(CREATE_SQL)
        if conn.execute("SELECT 1 FROM todos LIMIT 1").fetchone() is None:
            conn.executemany("INSERT INTO todos (name, completed) VALUES (?, ?)", SEEDS)
        conn.commit()
    finally:
        conn.close()


def list_todos():
    conn = _connect()
    try:
        rows = conn.execute("SELECT id, name, completed FROM todos ORDER BY id")
        return [
            {"id": r["id"], "name": r["name"], "completed": bool(r["completed"])}
            for r in rows
        ]
    finally:
        conn.close()


def add_todo(name: str) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("name 不能为空")
    conn = _connect()
    try:
        cur = conn.execute("INSERT INTO todos (name, completed) VALUES (?, 0)", (name,))
        conn.commit()
        return {"id": cur.lastrowid, "name": name, "completed": False}
    finally:
        conn.close()


def remove_todo(todo_id: int) -> bool:
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()