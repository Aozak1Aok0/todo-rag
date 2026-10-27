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
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

TMP_DIR = Path(tempfile.mkdtemp(prefix="todo-multi-"))
os.environ["TODO_DB"] = str(TMP_DIR / "test.db")

import main  # noqa: E402
from agents import orchestrator  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from store import add_todo  # noqa: E402


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


def route_json(route, docs="", todos=""):
    return json.dumps(
        {"route": route, "reason": "test", "todos_query": todos, "docs_query": docs},
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
    assert orchestrator.parse_plan(route_json("docs"), "q")["route"] == "docs"
    both = orchestrator.parse_plan(
        route_json("both", docs="检索实现", todos="全部待办"), "q"
    )
    assert both["route"] == "both"
    assert both["docs_query"] == "检索实现"
    assert both["todos_query"] == "全部待办"
    assert orchestrator.parse_plan("不是 JSON", "原问题")["route"] == "docs"
    return "todos/docs/both/fallback"


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
    assert blocked["write_blocked"] and "只读" in blocked["answer"]
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
