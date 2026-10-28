r"""待确认写操作的短期存储。

只做单进程、单用户的内存 proposal；不把 token 写盘。
生产多 worker / 多用户时需要换成数据库或带签名的审批 token。
"""

import secrets
import threading
import time
from datetime import datetime

DEFAULT_TTL = 300


class ProposalError(Exception):
    """proposal 审批失败的基类。"""


class ProposalNotFound(ProposalError):
    """proposal 不存在、已消费或已取消。"""


class ProposalExpired(ProposalError):
    """proposal 超过有效期。"""


class ProposalConflict(ProposalError):
    """执行时目标数据已变化（例如待办被别处删了）。"""


class ProposalStore:
    def __init__(self, ttl=DEFAULT_TTL):
        self.ttl = ttl
        self._items = {}
        self._lock = threading.Lock()

    def reset(self):
        """测试用：清空所有 proposal。"""
        with self._lock:
            self._items.clear()

    def _purge(self, now):
        expired = [k for k, v in self._items.items() if v["expires_at"] <= now]
        for k in expired:
            self._items.pop(k, None)

    def _public(self, item):
        left = max(0, int(item["expires_at"] - time.time()))
        return {
            "id": item["id"],
            "action": item["action"],
            "args": dict(item["args"]),
            "summary": item["summary"],
            "reason": item.get("reason", ""),
            "status": "pending",
            "created_at": datetime.fromtimestamp(item["created_at"]).isoformat(timespec="seconds"),
            "expires_at": datetime.fromtimestamp(item["expires_at"]).isoformat(timespec="seconds"),
            "expires_in_seconds": left,
        }

    def create(self, action, args, summary, reason=""):
        now = time.time()
        item = {
            "id": secrets.token_urlsafe(18),
            "action": action,
            "args": dict(args),
            "summary": summary,
            "reason": reason,
            "created_at": now,
            "expires_at": now + self.ttl,
        }
        with self._lock:
            self._purge(now)
            self._items[item["id"]] = item
            return self._public(item)

    def _take(self, proposal_id):
        now = time.time()
        with self._lock:
            item = self._items.get(proposal_id)
            if item is None:
                self._purge(now)
                raise ProposalNotFound(proposal_id)
            if item["expires_at"] <= now:
                self._items.pop(proposal_id, None)
                raise ProposalExpired(proposal_id)
            self._purge(now)
            return self._items.pop(proposal_id)

    def consume(self, proposal_id):
        """取出并作废一个 proposal；调用方随后执行动作。"""
        item = self._take(proposal_id)
        return self._public(item)

    def cancel(self, proposal_id):
        item = self._take(proposal_id)
        item["status"] = "cancelled"
        pub = self._public(item)
        pub["status"] = "cancelled"
        return pub


store = ProposalStore()


def create_proposal(action, args, summary, reason=""):
    return store.create(action, args, summary, reason)


def consume_proposal(proposal_id):
    return store.consume(proposal_id)


def cancel_proposal(proposal_id):
    return store.cancel(proposal_id)


def reset():
    store.reset()
