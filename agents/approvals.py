r"""待确认写操作的 SQLite 存储。

proposal 与 todos 共用同一个 `TODO_DB`，但使用独立的 `agent_proposals` 表。
这样服务重启、单进程多 worker 都不会丢 proposal；公网多用户仍需要额外的登录态/权限绑定。
"""

import json
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime

from store import db_path

DEFAULT_TTL = 300
TABLE = "agent_proposals"
STALE_SECONDS = int(os.getenv("PROPOSAL_STALE_SECONDS", "60"))
ALLOWED_STATUSES = {"pending", "executing", "executed", "cancelled", "failed", "expired"}

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


def _iso(ts):
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds") if ts else None


def _p95(values):
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]


def _public(row, status=None):
    left = max(0, int(row["expires_at"] - time.time()))
    return {
        "id": row["id"],
        "action": row["action"],
        "args": json.loads(row["args_json"]),
        "summary": row["summary"],
        "reason": row["reason"] or "",
        "status": status or row["status"],
        "created_at": _iso(row["created_at"]),
        "expires_at": _iso(row["expires_at"]),
        "expires_in_seconds": left,
    }


def _audit(row):
    return {
        "id": row["id"],
        "action": row["action"],
        "args": json.loads(row["args_json"]),
        "summary": row["summary"],
        "reason": row["reason"] or "",
        "status": row["status"],
        "created_at": _iso(row["created_at"]),
        "expires_at": _iso(row["expires_at"]),
        "claimed_at": _iso(row["claimed_at"]),
        "finished_at": _iso(row["finished_at"]),
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
    }


class ProposalStore:
    def __init__(self, ttl=DEFAULT_TTL, stale_seconds=None):
        self.ttl = ttl
        self.stale_seconds = STALE_SECONDS if stale_seconds is None else stale_seconds
        self._lock = threading.Lock()

    def _recover(self, conn, now):
        cur = conn.execute(
            f"UPDATE {TABLE} SET status='failed', finished_at=?, result_json=? "
            "WHERE status='executing' AND claimed_at IS NOT NULL AND claimed_at <= ?",
            (
                now,
                json.dumps({"error": "stale_executing"}, ensure_ascii=False),
                now - self.stale_seconds,
            ),
        )
        return cur.rowcount

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
            self._recover(conn, now)
            conn.execute(
                f"UPDATE {TABLE} SET status='expired', finished_at=? "
                "WHERE status='pending' AND expires_at <= ?",
                (now, now),
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
            self._recover(conn, now)
            conn.commit()
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
                    f"UPDATE {TABLE} SET status='expired', finished_at=? "
                    "WHERE id=? AND status='pending'",
                    (now, proposal_id),
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
            self._recover(conn, now)
            conn.commit()
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
                    f"UPDATE {TABLE} SET status='expired', finished_at=? "
                    "WHERE id=? AND status='pending'",
                    (now, proposal_id),
                )
                conn.commit()
                raise ProposalExpired(proposal_id)
            raise ProposalNotFound(proposal_id)
        finally:
            conn.close()

    def list(self, status=None, limit=20, offset=0):
        now = time.time()
        conn = _connect()
        try:
            _ensure(conn)
            self._recover(conn, now)
            conn.commit()
            where, params = "", []
            if status:
                where = "WHERE status = ?"
                params.append(status)
            total = conn.execute(
                f"SELECT COUNT(*) FROM {TABLE} {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM {TABLE} {where} "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
            return {
                "items": [_audit(r) for r in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        finally:
            conn.close()

    def get(self, proposal_id):
        conn = _connect()
        try:
            _ensure(conn)
            self._recover(conn, time.time())
            conn.commit()
            row = conn.execute(
                f"SELECT * FROM {TABLE} WHERE id = ?", (proposal_id,)
            ).fetchone()
            return _audit(row) if row else None
        finally:
            conn.close()

    def summarize(self, days=7):
        days = max(1, min(int(days), 90))
        now = time.time()
        start = now - days * 86400
        conn = _connect()
        try:
            _ensure(conn)
            self._recover(conn, now)
            conn.commit()
            rows = conn.execute(
                f"SELECT * FROM {TABLE} WHERE created_at >= ? ORDER BY created_at",
                (start,),
            ).fetchall()
        finally:
            conn.close()

        by_status = {s: 0 for s in ALLOWED_STATUSES}
        by_action = {}
        decision_ms = []
        stale_recovered = 0
        oldest_pending = 0
        oldest_executing = 0

        for row in rows:
            status = row["status"]
            by_status[status] = by_status.get(status, 0) + 1
            action = row["action"]
            bucket = by_action.setdefault(
                action,
                {"action": action, "total": 0, **{s: 0 for s in ALLOWED_STATUSES}},
            )
            bucket["total"] += 1
            bucket[status] = bucket.get(status, 0) + 1

            if row["finished_at"]:
                decision_ms.append(max(0, int((row["finished_at"] - row["created_at"]) * 1000)))
            if status == "pending":
                oldest_pending = max(oldest_pending, now - row["created_at"])
            elif status == "executing" and row["claimed_at"]:
                oldest_executing = max(oldest_executing, now - row["claimed_at"])
            if status == "failed" and row["result_json"]:
                try:
                    error = json.loads(row["result_json"]).get("error")
                except (TypeError, json.JSONDecodeError):
                    error = None
                if error == "stale_executing":
                    stale_recovered += 1

        total = len(rows)
        decided = (
            by_status.get("executed", 0)
            + by_status.get("cancelled", 0)
            + by_status.get("failed", 0)
            + by_status.get("expired", 0)
        )

        def rate(n):
            return round(n / decided, 3) if decided else 0.0

        return {
            "window_days": days,
            "total": total,
            "by_status": by_status,
            "by_action": sorted(by_action.values(), key=lambda x: -x["total"]),
            "decided": decided,
            "approval_rate": rate(by_status.get("executed", 0)),
            "cancel_rate": rate(by_status.get("cancelled", 0)),
            "failure_rate": rate(by_status.get("failed", 0)),
            "stale_recovered": stale_recovered,
            "avg_decision_ms": round(sum(decision_ms) / len(decision_ms)) if decision_ms else 0,
            "p95_decision_ms": _p95(decision_ms),
            "oldest_pending_seconds": int(oldest_pending),
            "oldest_executing_seconds": int(oldest_executing),
        }

    def recover_stale(self):
        now = time.time()
        conn = _connect()
        try:
            _ensure(conn)
            changed = self._recover(conn, now)
            conn.commit()
            return changed
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


def list_proposals(status=None, limit=20, offset=0):
    return store.list(status, limit, offset)


def get_proposal(proposal_id):
    return store.get(proposal_id)


def summarize_proposals(days=7):
    return store.summarize(days)


def recover_stale_proposals():
    return store.recover_stale()


def reset():
    store.reset()
