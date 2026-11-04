"""proposal 生命周期测试：TTL、单次消费、取消、过期。纯 SQLite，无外部依赖。"""

import time

import pytest
from agents.approvals import ProposalExpired, ProposalNotFound, ProposalStore


@pytest.fixture
def proposal_store(todo_db):
    store = ProposalStore(ttl=60)
    store.reset()
    return store


def test_create_is_pending(proposal_store):
    p = proposal_store.create("add_todo", {"name": "写测试"}, "新增待办：写测试")
    assert p["status"] == "pending"
    assert p["action"] == "add_todo"
    assert p["summary"] == "新增待办：写测试"
    assert proposal_store.get(p["id"])["status"] == "pending"


def test_claim_is_single_use(proposal_store):
    p = proposal_store.create("delete_todo", {"id": 1}, "删除 #1")
    claimed = proposal_store.claim(p["id"])
    assert claimed["status"] == "executing"
    with pytest.raises(ProposalNotFound):
        proposal_store.claim(p["id"])


def test_finish_executed(proposal_store):
    p = proposal_store.create("set_completed", {"id": 2, "completed": True}, "完成 #2")
    proposal_store.claim(p["id"])
    done = proposal_store.finish(p["id"], "executed", {"ok": True})
    assert done["status"] == "executed"
    with pytest.raises(ProposalNotFound):
        proposal_store.claim(p["id"])


def test_cancel_then_claim_fails(proposal_store):
    p = proposal_store.create("add_todo", {"name": "x"}, "新增")
    assert proposal_store.cancel(p["id"])["status"] == "cancelled"
    with pytest.raises(ProposalNotFound):
        proposal_store.claim(p["id"])


def test_expired_proposal_cannot_be_claimed(todo_db):
    store = ProposalStore(ttl=0.05)
    store.reset()
    p = store.create("add_todo", {"name": "过期"}, "新增")
    time.sleep(0.12)
    with pytest.raises(ProposalExpired):
        store.claim(p["id"])
    assert store.get(p["id"])["status"] == "expired"


def test_unknown_id(proposal_store):
    assert proposal_store.get("not-exist") is None
    with pytest.raises(ProposalNotFound):
        proposal_store.claim("not-exist")


def test_summarize_counts_by_status(proposal_store):
    a = proposal_store.create("add_todo", {"name": "a"}, "a")
    b = proposal_store.create("add_todo", {"name": "b"}, "b")
    proposal_store.cancel(b["id"])
    proposal_store.claim(a["id"])
    proposal_store.finish(a["id"], "executed")

    summary = proposal_store.summarize(days=7)
    assert summary["total"] == 2
    assert summary["by_status"]["executed"] == 1
    assert summary["by_status"]["cancelled"] == 1
    assert summary["approval_rate"] == 0.5
