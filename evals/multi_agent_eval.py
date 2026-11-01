r"""多 Agent 端到端评测：路由 + 回答 + 写 proposal + 批准执行。

用法：
    .\.venv\Scripts\python.exe evals\multi_agent_eval.py
    .\.venv\Scripts\python.exe evals\multi_agent_eval.py --limit 3

写操作用临时 TODO_DB，不会碰真实 todos.db。
"""

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="multi-agent-eval-"))
os.environ["TODO_DB"] = str(TMP / "eval.db")
os.environ["OBS_DIR"] = str(TMP / "logs")
sys.path.insert(0, str(APP))

from openai import AsyncOpenAI  # noqa: E402
from credentials import get_deepseek_key  # noqa: E402
from agents.approvals import (  # noqa: E402
    claim_proposal,
    finish_proposal,
    reset as reset_proposals,
)
from agents.orchestrator import run_multi_agent  # noqa: E402
from agents.todo_writes import execute_proposal  # noqa: E402
from store import init_db, list_todos  # noqa: E402

CASES = [
    {
        "id": "E1",
        "question": "Swagger 白屏是怎么解决的？",
        "route": "docs",
        "keywords": ["Swagger"],
    },
    {
        "id": "E2",
        "question": "todos 表里有哪些字段？",
        "route": "docs",
        "keywords": ["id", "name", "completed"],
    },
    {
        "id": "E3",
        "question": "现在一共有多少条待办？",
        "route": "todos",
        "keywords": ["3"],
    },
    {
        "id": "E4",
        "question": "现在有多少条待办？顺便说明 Swagger 白屏怎么解决",
        "route": "both",
        "keywords": ["待办", "Swagger"],
    },
    {
        "id": "E5",
        "question": "把「多 Agent 评测」加到待办",
        "route": "todos",
        "intent": "write",
        "action": "add_todo",
        "name": "多 Agent 评测",
    },
    {
        "id": "E6",
        "question": "把「多 Agent 评测」标记为已完成",
        "route": "todos",
        "intent": "write",
        "action": "set_completed",
        "name": "多 Agent 评测",
        "completed": True,
    },
    {
        "id": "E7",
        "question": "删除「多 Agent 评测」这条待办",
        "route": "todos",
        "intent": "write",
        "action": "delete_todo",
        "name": "多 Agent 评测",
    },
    {
        "id": "E8",
        "question": "删除 9999 号待办",
        "route": "todos",
        "intent": "write",
        "clarify": True,
    },
]


def _todo_by_name(name):
    return next((t for t in list_todos() if t["name"] == name), None)


def _approve(proposal_id):
    proposal = claim_proposal(proposal_id)
    try:
        result = execute_proposal(proposal)
    except Exception as e:  # noqa: BLE001
        finish_proposal(proposal_id, "failed", {"error": str(e)})
        raise
    finish_proposal(proposal_id, "executed", result)
    return result


async def run(limit=0, k=10, out=None):
    init_db()
    reset_proposals()
    client = AsyncOpenAI(api_key=get_deepseek_key(), base_url="https://api.deepseek.com")
    cases = CASES[:limit] if limit else CASES
    rows = []

    for case in cases:
        t0 = time.time()
        result = await run_multi_agent(
            client, case["question"], k=k, multi_query=True
        )
        row = {
            "id": case["id"],
            "question": case["question"],
            "expected_route": case["route"],
            "actual_route": result["route"],
            "expected_intent": case.get("intent", "read"),
            "actual_intent": result["plan"].get("intent"),
            "status": result["status"],
            "answer": result["answer"],
            "sources": result["sources"],
            "verification": result.get("verification"),
            "trace": result["trace"],
            "usage": result["usage"],
            "latency_ms": int((time.time() - t0) * 1000),
        }

        checks = [
            result["route"] == case["route"],
            result["plan"].get("intent") == case.get("intent", "read"),
        ]
        if case.get("keywords"):
            answer_lower = result["answer"].lower()
            checks.append(all(k.lower() in answer_lower for k in case["keywords"]))

        if case.get("clarify"):
            checks.append(result["status"] == "needs_clarification")
            checks.append(result["proposal"] is None)
        elif case.get("action"):
            checks.append(result["status"] == "approval_required")
            proposal = result.get("proposal") or {}
            row["proposal_action"] = proposal.get("action")
            row["proposal_args"] = proposal.get("args")
            checks.append(proposal.get("action") == case["action"])
            if proposal.get("action") == case["action"]:
                executed = _approve(proposal["id"])
                row["execution"] = executed
                if case["action"] == "add_todo":
                    checks.append(_todo_by_name(case["name"]) is not None)
                elif case["action"] == "set_completed":
                    todo = _todo_by_name(case["name"])
                    checks.append(todo is not None and todo["completed"] is True)
                elif case["action"] == "delete_todo":
                    checks.append(_todo_by_name(case["name"]) is None)
            else:
                checks.append(False)
        else:
            checks.append(result["status"] == "ok")

        row["ok"] = all(checks)
        rows.append(row)
        mark = "PASS" if row["ok"] else "FAIL"
        print(
            f"{mark}  {case['id']:<3} route={row['actual_route']:<5} "
            f"intent={row['actual_intent']:<5} status={row['status']:<20} "
            f"sources={len(row['sources'])} {row['latency_ms']}ms"
        )

    dest = out or APP / "evals" / f"multi-agent-{datetime.now():%Y%m%d}.jsonl"
    dest.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    passed = sum(1 for r in rows if r["ok"])
    tin = sum(r["usage"]["in"] for r in rows)
    tout = sum(r["usage"]["out"] for r in rows)
    print(f"\n{passed}/{len(rows)} 通过 · tokens {tin}/{tout} · 输出 {dest}")
    return passed == len(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    try:
        ok = asyncio.run(run(args.limit, args.k, Path(args.out) if args.out else None))
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    if not ok:
        sys.exit(1)
