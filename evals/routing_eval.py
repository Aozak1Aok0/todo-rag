r"""Supervisor 路由评测：10 条人工标注的 todo / docs / both 问题。

用法：
    .\.venv\Scripts\python.exe evals\routing_eval.py
    .\.venv\Scripts\python.exe evals\routing_eval.py --limit 3
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from openai import AsyncOpenAI  # noqa: E402

from agents.orchestrator import plan_route  # noqa: E402
from credentials import get_deepseek_key  # noqa: E402

CASES = [
    ("R1", "我最新的待办有哪些？", "todos", "read"),
    ("R2", "有哪些事项还没完成？", "todos", "read"),
    ("R3", "Swagger 白屏是怎么解决的？", "docs", "read"),
    ("R4", "todos 表有哪些字段？", "docs", "read"),
    ("R5", "Express 和 FastAPI 版的数据层有什么不同？", "docs", "read"),
    ("R6", "列出我的待办，并说明 /rag-verify 是怎么做校验的", "both", "read"),
    ("R7", "待办里有什么，另外 RAG 检索是怎么实现的？", "both", "read"),
    ("R8", "这个服务支持多用户吗？", "docs", "read"),
    ("R9", "有哪些未完成待办，顺便说下 /rag 的 k 默认值", "both", "read"),
    ("R10", "把「学 Rust」加到待办里", "todos", "write"),
]


async def run(limit=0, out=None):
    client = AsyncOpenAI(api_key=get_deepseek_key(), base_url="https://api.deepseek.com")
    cases = CASES[:limit] if limit else CASES
    rows, t_all = [], time.time()
    for cid, question, expected, expected_intent in cases:
        t0 = time.time()
        plan, usage = await plan_route(client, question)
        actual = plan["route"]
        actual_intent = plan["intent"]
        route_ok = actual == expected
        intent_ok = actual_intent == expected_intent
        rows.append({
            "id": cid,
            "question": question,
            "expected": expected,
            "actual": actual,
            "expected_intent": expected_intent,
            "actual_intent": actual_intent,
            "route_ok": route_ok,
            "intent_ok": intent_ok,
            "ok": route_ok and intent_ok,
            "reason": plan.get("reason"),
            "todos_query": plan.get("todos_query"),
            "docs_query": plan.get("docs_query"),
            "latency_ms": int((time.time() - t0) * 1000),
            "usage": usage,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        })
        mark = "PASS" if rows[-1]["ok"] else "FAIL"
        print(f"{mark}  {cid:<3} route={actual:<5}/{expected:<5} "
              f"intent={actual_intent:<5}/{expected_intent:<5} "
              f"{rows[-1]['latency_ms']}ms  {question}")

    dest = out or APP / "evals" / f"routing-{datetime.now():%Y%m%d}.jsonl"
    dest.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    passed = sum(1 for r in rows if r["ok"])
    print(f"\n{passed}/{len(rows)} 路由+intent 正确 · {time.time() - t_all:.1f}s")
    print(f"输出：{dest}")
    return passed == len(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    ok = asyncio.run(run(args.limit, Path(args.out) if args.out else None))
    if not ok:
        sys.exit(1)
