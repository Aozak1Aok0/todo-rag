r"""多 Agent 冒烟测试（不联网、不花 token）。

用法：
    .\.venv\Scripts\python.exe tests\multi_agent_smoke.py
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

TMP_DIR = Path(tempfile.mkdtemp(prefix="todo-multi-"))
os.environ["TODO_DB"] = str(TMP_DIR / "test.db")

import main  # noqa: E402
from agents import approvals, orchestrator  # noqa: E402
from agents.approvals import ProposalExpired, ProposalStore  # noqa: E402
from agents.write_planner import parse_proposal  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from store import add_todo, list_todos, remove_todo  # noqa: E402


class _Usage:
    def __init__(self, inp, out):
        self.prompt_tokens = inp
        self.completion_tokens = out


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content, inp=10, out=5):
        self.choices = [_Choice(content)]
        self.usage = _Usage(inp, out)


class _Completions:
    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = []

    async def create(self, **kw):
        self.calls.append(kw)
        return _Resp(self.texts.pop(0))


class _Chat:
    def __init__(self, texts):
        self.completions = _Completions(texts)


class FakeClient:
    def __init__(self, texts):
        self.chat = _Chat(texts)


def route_json(route, docs="", todos="", intent="read"):
    return json.dumps(
        {
            "route": route,
            "intent": intent,
            "reason": "test",
            "todos_query": todos,
            "docs_query": docs,
        },
        ensure_ascii=False,
    )


def docs_stub(calls):
    async def _run(client, question, k, multi_query):
        calls.append({
            "question": question, "k": k, "multi_query": multi_query,
        })
        return {
            "answer": "文档答案：使用混合检索。",
            "hits": [{
                "source": "rag/rag.py",
                "start_line": 1,
                "end_line": 2,
                "distance": 0.1,
                "text": "def retrieve():\n    pass",
            }],
            "verification": {"verdict": "ok", "unsupported": [], "reason": "ok"},
            "rounds": 1,
            "usage": {"in": 20, "out": 8},
        }
    return _run


def t1_parse_plan():
    assert orchestrator.parse_plan(route_json("todos"), "q")["route"] == "todos"
    assert orchestrator.parse_plan(route_json("todos"), "q")["intent"] == "read"
    assert orchestrator.parse_plan(
        route_json("todos", intent="write"), "q"
    )["intent"] == "write"
    assert orchestrator.parse_plan(route_json("docs"), "q")["route"] == "docs"
    both = orchestrator.parse_plan(
        route_json("both", docs="检索实现", todos="全部待办"), "q"
    )
    assert both["route"] == "both"
    assert both["docs_query"] == "检索实现"
    assert both["todos_query"] == "全部待办"
    assert orchestrator.parse_plan("不是 JSON", "原问题")["route"] == "docs"
    assert orchestrator.parse_plan("不是 JSON", "把学 Rust 加到待办")["intent"] == "write"
    todos = [{"id": 1, "name": "x", "completed": False}]
    assert parse_proposal(
        '{"action":"complete_todo","args":{"todo_id":1}}', todos
    )["args"]["completed"] is True
    return "todos/docs/both/fallback/intent/alias"


def t2_todos_worker():
    add_todo("多 Agent 测试待办")
    all_res = orchestrator.answer_todos("列出全部待办")
    open_res = orchestrator.answer_todos("还有哪些未完成？")
    done_res = orchestrator.answer_todos("已完成的有哪些？")
    count_res = orchestrator.answer_todos("我有多少条待办、多少条未完成？")
    blocked = orchestrator.answer_todos("把学 Rust 加到待办")
    assert "多 Agent 测试待办" in all_res["answer"]
    assert all(not t["completed"] for t in open_res["selected"])
    assert all(t["completed"] for t in done_res["selected"])
    assert count_res["count_only"] and "全部" in count_res["answer"]
    assert "\n1." not in count_res["answer"]
    assert "全部" in all_res["answer"]
    assert blocked["write_blocked"] and "proposal" in blocked["answer"]
    return (
        f"all={len(all_res['selected'])} open={len(open_res['selected'])} "
        f"done={len(done_res['selected'])} count_only write_blocked"
    )


def t3_route_todos():
    fake = FakeClient([route_json("todos", todos="列出全部待办")])
    docs_calls = []
    res = asyncio.run(
        orchestrator.run_multi_agent(
            fake, "列出全部待办", k=10, docs_worker=docs_stub(docs_calls)
        )
    )
    assert res["route"] == "todos"
    assert not docs_calls
    assert [t["agent"] for t in res["trace"]] == ["supervisor", "todos"]
    assert "多 Agent 测试待办" in res["answer"]
    return f"agents={len(res['trace'])}"


def t4_route_docs():
    fake = FakeClient([route_json("docs", docs="检索怎么实现")])
    docs_calls = []
    res = asyncio.run(
        orchestrator.run_multi_agent(
            fake, "检索怎么实现", k=10, docs_worker=docs_stub(docs_calls)
        )
    )
    assert res["route"] == "docs"
    assert docs_calls and docs_calls[0]["question"] == "检索怎么实现"
    assert res["answer"] == "文档答案：使用混合检索。"
    assert [t["agent"] for t in res["trace"]] == ["supervisor", "docs"]
    assert len(res["sources"]) == 1
    return f"agents={len(res['trace'])} sources={len(res['sources'])}"


def t5_route_both():
    fake = FakeClient([
        route_json("both", docs="检索怎么实现", todos="列出全部待办"),
        "【待办】有测试待办。\n\n【文档】使用混合检索。",
    ])
    docs_calls = []
    res = asyncio.run(
        orchestrator.run_multi_agent(
            fake, "列出待办并说明检索", k=10, docs_worker=docs_stub(docs_calls)
        )
    )
    assert res["route"] == "both"
    assert docs_calls
    assert [t["agent"] for t in res["trace"]] == [
        "supervisor", "todos", "docs", "synthesizer",
    ]
    assert res["answer"].startswith("【待办】")
    assert res["usage"]["in"] == 40  # supervisor 10 + docs 20 + synth 10
    return f"agents={len(res['trace'])} tokens={res['usage']}"


def t6_endpoint():
    fake = FakeClient([route_json("docs", docs="检索怎么实现")])
    docs_calls = []
    old_get_client = main.get_client
    old_docs_worker = orchestrator._docs_worker
    main.get_client = lambda: fake
    orchestrator._docs_worker = docs_stub(docs_calls)
    try:
        c = TestClient(main.app)
        r = c.post("/multi-agent", json={"question": "检索怎么实现", "k": 10})
        assert r.status_code == 200
        body = r.json()
        assert body["route"] == "docs"
        assert body["answer"]
        assert body["trace"][0]["agent"] == "supervisor"
    finally:
        main.get_client = old_get_client
        orchestrator._docs_worker = old_docs_worker
    return f"status={r.status_code} route={body['route']}"


def make_write_proposal(question, action_json, name_for_check, must_not_exist=True):
    approvals.reset()
    fake = FakeClient([
        route_json("todos", todos=question, intent="write"),
        action_json,
    ])
    res = asyncio.run(orchestrator.run_multi_agent(fake, question, k=10))
    assert res["status"] == "approval_required"
    assert res["proposal"]["action"]
    if must_not_exist:
        assert all(t["name"] != name_for_check for t in list_todos())
    return res


def t7_write_proposal():
    res = make_write_proposal(
        "把学 Rust 加到待办",
        json.dumps({"action": "add_todo", "args": {"name": "学 Rust"}, "reason": "test"}),
        "学 Rust",
    )
    assert res["proposal"]["action"] == "add_todo"
    assert res["trace"][1]["agent"] == "todo_planner"
    assert "确认后才会执行" in res["answer"]
    return f"proposal={res['proposal']['action']} status={res['status']}"


def t8_approve_executes():
    res = make_write_proposal(
        "把学 Go 加到待办",
        json.dumps({"action": "add_todo", "args": {"name": "学 Go"}, "reason": "test"}),
        "学 Go",
    )
    pid = res["proposal"]["id"]
    c = TestClient(main.app)
    missing = c.post("/multi-agent/approve", json={"proposal_id": pid})
    assert missing.status_code == 422
    r = c.post("/multi-agent/approve", json={"proposal_id": pid, "approved": True})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "executed"
    assert any(t["name"] == "学 Go" for t in list_todos())
    again = c.post("/multi-agent/approve", json={"proposal_id": pid, "approved": True})
    assert again.status_code == 404
    return f"status={body['status']} single_use={again.status_code}"


def t9_cancel_does_nothing():
    res = make_write_proposal(
        "把学 Rust2 加到待办",
        json.dumps({"action": "add_todo", "args": {"name": "学 Rust2"}, "reason": "test"}),
        "学 Rust2",
    )
    c = TestClient(main.app)
    r = c.post(
        "/multi-agent/approve",
        json={"proposal_id": res["proposal"]["id"], "approved": False},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert all(t["name"] != "学 Rust2" for t in list_todos())
    return "cancelled"


def t10_invalid_id_needs_clarification():
    approvals.reset()
    q = "删除 9999 号待办"
    fake = FakeClient([
        route_json("todos", todos=q, intent="write"),
        json.dumps({"action": "delete_todo", "args": {"todo_id": 9999}, "reason": "test"}),
    ])
    res = asyncio.run(orchestrator.run_multi_agent(fake, q, k=10))
    assert res["status"] == "needs_clarification"
    assert res["proposal"] is None
    assert "没有找到待办" in res["answer"]
    return "no proposal"


def t11_set_completed_after_approval():
    todo = add_todo("待确认完成")
    res = make_write_proposal(
        "把待确认完成标记为已完成",
        json.dumps({
            "action": "set_completed",
            "args": {"todo_id": todo["id"], "completed": True},
            "reason": "test",
        }),
        "待确认完成",
        must_not_exist=False,
    )
    c = TestClient(main.app)
    r = c.post(
        "/multi-agent/approve",
        json={"proposal_id": res["proposal"]["id"], "approved": True},
    )
    assert r.status_code == 200
    assert r.json()["result"]["todo"]["completed"] is True
    return "completed"


def t12_proposal_expiry():
    s = ProposalStore(ttl=0)
    p = s.create("add_todo", {"name": "过期"}, "过期测试")
    try:
        s.consume(p["id"])
    except ProposalExpired:
        return "expired"
    raise AssertionError("过期 proposal 不应被消费")


def t13_stale_target_conflict():
    todo = add_todo("冲突测试")
    res = make_write_proposal(
        "删除冲突测试",
        json.dumps({
            "action": "delete_todo",
            "args": {"todo_id": todo["id"]},
            "reason": "test",
        }),
        "冲突测试",
        must_not_exist=False,
    )
    remove_todo(todo["id"])
    c = TestClient(main.app)
    r = c.post(
        "/multi-agent/approve",
        json={"proposal_id": res["proposal"]["id"], "approved": True},
    )
    assert r.status_code == 409
    return f"status={r.status_code}"


def t14_expired_http():
    res = make_write_proposal(
        "把学 Rust3 加到待办",
        json.dumps({"action": "add_todo", "args": {"name": "学 Rust3"}, "reason": "test"}),
        "学 Rust3",
    )
    pid = res["proposal"]["id"]
    approvals.store._items[pid]["expires_at"] = time.time() - 1
    c = TestClient(main.app)
    r = c.post("/multi-agent/approve", json={"proposal_id": pid, "approved": True})
    assert r.status_code == 410
    return f"status={r.status_code}"


def t15_write_plus_docs():
    approvals.reset()
    q = "把学 Kotlin 加到待办，并说明检索怎么实现"
    fake = FakeClient([
        route_json("both", docs="检索怎么实现", todos=q, intent="write"),
        json.dumps({"action": "add_todo", "args": {"name": "学 Kotlin"}, "reason": "test"}),
    ])
    docs_calls = []
    res = asyncio.run(
        orchestrator.run_multi_agent(
            fake, q, k=10, docs_worker=docs_stub(docs_calls)
        )
    )
    agents = [t["agent"] for t in res["trace"]]
    assert res["route"] == "both"
    assert res["status"] == "approval_required"
    assert res["proposal"]["action"] == "add_todo"
    assert docs_calls
    assert agents == ["supervisor", "todo_planner", "docs"]
    assert "【文档】" in res["answer"]
    assert "确认后才会执行" in res["answer"]
    return f"agents={agents}"


def run(name, fn):
    try:
        return name, True, fn() or ""
    except Exception as e:  # noqa: BLE001
        return name, False, f"{type(e).__name__}: {e}"


def main_run():
    results = [
        run("T1 路由解析", t1_parse_plan),
        run("T2 待办 worker", t2_todos_worker),
        run("T3 只走待办", t3_route_todos),
        run("T4 只走文档", t4_route_docs),
        run("T5 双路由汇总", t5_route_both),
        run("T6 HTTP 端点", t6_endpoint),
        run("T7 写 proposal", t7_write_proposal),
        run("T8 确认执行", t8_approve_executes),
        run("T9 取消不落库", t9_cancel_does_nothing),
        run("T10 非法 id", t10_invalid_id_needs_clarification),
        run("T11 标记完成", t11_set_completed_after_approval),
        run("T12 proposal 过期", t12_proposal_expiry),
        run("T13 目标已变化", t13_stale_target_conflict),
        run("T14 过期 HTTP", t14_expired_http),
        run("T15 写入 + 文档", t15_write_plus_docs),
    ]
    print()
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<18} {detail}")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} 通过")
    shutil.rmtree(TMP_DIR, ignore_errors=True)
    if passed != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main_run()
