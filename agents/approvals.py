r"""待确认写操作的 SQLite 存储。

proposal 与 todos 共用同一个 `TODO_DB`，但使用独立的 `agent_proposals` 表。
这样服务重启、单进程多 worker 都不会丢 proposal；公网多用户仍需要额外的登录态/权限绑定。
"""

import json
import secrets
import sqlite3
import threading
import time
from datetime import datetime

from store import db_path

DEFAULT_TTL = 300
TABLE = "agent_proposals"

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    args_json TEXT NOT NULL,
    summary TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    claimed_at REAL,
    finished_at REAL,
    result_json TEXT
)
"""

_INDEX = (
    f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_status_expires "
    f"ON {TABLE}(status, expires_at)"
)


class ProposalError(Exception):
    """proposal 审批失败的基类。"""


class ProposalNotFound(ProposalError):
    """proposal 不存在、已消费、已取消或已失败。"""


class ProposalExpired(ProposalError):
    """proposal 超过有效期。"""


class ProposalConflict(ProposalError):
    """执行时目标数据已变化（例如待办被别处删了）。"""


def _connect():
    conn = sqlite3.connect(db_path(), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure(conn):
    conn.execute(_SCHEMA)
    conn.execute(_INDEX)


def _public(row, status=None):
    left = max(0, int(row["expires_at"] - time.time()))
    return {
        "id": row["id"],
        "action": row["action"],
        "args": json.loads(row["args_json"]),
        "summary": row["summary"],
        "reason": row["reason"] or "",
        "status": status or row["status"],
        "created_at": datetime.fromtimestamp(row["created_at"]).isoformat(timespec="seconds"),
        "expires_at": datetime.fromtimestamp(row["expires_at"]).isoformat(timespec="seconds"),
        "expires_in_seconds": left,
    }


class ProposalStore:
    def __init__(self, ttl=DEFAULT_TTL):
        self.ttl = ttl
        self._lock = threading.Lock()

    def reset(self):
        """测试用：清空所有 proposal。"""
        with self._lock:
            conn = _connect()
            try:
                _ensure(conn)
                conn.execute(f"DELETE FROM {TABLE}")
                conn.commit()
            finally:
                conn.close()

    def create(self, action, args, summary, reason=""):
        now = time.time()
        proposal_id = secrets.token_urlsafe(18)
        conn = _connect()
        try:
            _ensure(conn)
            conn.execute(
                f"UPDATE {TABLE} SET status='expired' "
                "WHERE status='pending' AND expires_at <= ?",
                (now,),
            )
            conn.execute(
                f"INSERT INTO {TABLE} "
                "(id, action, args_json, summary, reason, status, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
                (
                    proposal_id,
                    action,
                    json.dumps(args, ensure_ascii=False),
                    summary,
                    reason,
                    now,
                    now + self.ttl,
                ),
            )
            conn.commit()
            row = conn.execute(
                f"SELECT * FROM {TABLE} WHERE id = ?", (proposal_id,)
            ).fetchone()
            return _public(row)
        finally:
            conn.close()

    def claim(self, proposal_id):
        """原子地把 pending 改成 executing；重复/取消/失败的 proposal 不再可用。"""
        now = time.time()
        conn = _connect()
        try:
            _ensure(conn)
            cur = conn.execute(
                f"UPDATE {TABLE} SET status='executing', claimed_at=? "
                "WHERE id=? AND status='pending' AND expires_at > ?",
                (now, proposal_id, now),
            )
            if cur.rowcount == 1:
                conn.commit()
                row = conn.execute(
                    f"SELECT * FROM {TABLE} WHERE id = ?", (proposal_id,)
                ).fetchone()
                return _public(row)

            conn.rollback()
            row = conn.execute(
                f"SELECT * FROM {TABLE} WHERE id = ?", (proposal_id,)
            ).fetchone()
            if row is None:
                raise ProposalNotFound(proposal_id)
            if row["status"] != "pending":
                raise ProposalNotFound(proposal_id)
            if row["expires_at"] <= now:
                conn.execute(
                    f"UPDATE {TABLE} SET status='expired' WHERE id=? AND status='pending'",
                    (proposal_id,),
                )
                conn.commit()
                raise ProposalExpired(proposal_id)
            raise ProposalNotFound(proposal_id)
        finally:
            conn.close()

    def cancel(self, proposal_id):
        now = time.time()
        conn = _connect()
        try:
            _ensure(conn)
            cur = conn.execute(
                f"UPDATE {TABLE} SET status='cancelled', finished_at=? "
                "WHERE id=? AND status='pending' AND expires_at > ?",
                (now, proposal_id, now),
            )
            if cur.rowcount == 1:
                conn.commit()
                row = conn.execute(
                    f"SELECT * FROM {TABLE} WHERE id = ?", (proposal_id,)
                ).fetchone()
                return _public(row)

            conn.rollback()
            row = conn.execute(
                f"SELECT * FROM {TABLE} WHERE id = ?", (proposal_id,)
            ).fetchone()
            if row is None:
                raise ProposalNotFound(proposal_id)
            if row["status"] != "pending":
                raise ProposalNotFound(proposal_id)
            if row["expires_at"] <= now:
                conn.execute(
                    f"UPDATE {TABLE} SET status='expired' WHERE id=? AND status='pending'",
                    (proposal_id,),
                )
                conn.commit()
                raise ProposalExpired(proposal_id)
            raise ProposalNotFound(proposal_id)
        finally:
            conn.close()

    def finish(self, proposal_id, status="executed", result=None):
        if status not in {"executed", "failed"}:
            raise ValueError(f"非法终态：{status}")
        conn = _connect()
        try:
            _ensure(conn)
            conn.execute(
                f"UPDATE {TABLE} SET status=?, finished_at=?, result_json=? "
                "WHERE id=? AND status='executing'",
                (
                    status,
                    time.time(),
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    proposal_id,
                ),
            )
            conn.commit()
            row = conn.execute(
                f"SELECT * FROM {TABLE} WHERE id = ?", (proposal_id,)
            ).fetchone()
            return _public(row) if row else None
        finally:
            conn.close()

    # 兼容旧调用名
    consume = claim


store = ProposalStore()


def create_proposal(action, args, summary, reason=""):
    return store.create(action, args, summary, reason)


def claim_proposal(proposal_id):
    return store.claim(proposal_id)


def consume_proposal(proposal_id):
    return store.claim(proposal_id)


def cancel_proposal(proposal_id):
    return store.cancel(proposal_id)


def finish_proposal(proposal_id, status="executed", result=None):
    return store.finish(proposal_id, status, result)


def reset():
    store.reset()
