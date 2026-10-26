r"""双 Agent 评测：对 10 题跑「回答 + 校验（必要时重写）」，保存逐题结果。

用法：
    .\.venv\Scripts\python.exe evals\verify_eval.py
    .\.venv\Scripts\python.exe evals\verify_eval.py --k 8 --limit 3
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

from credentials import get_deepseek_key  # noqa: E402
from rag import pipeline  # noqa: E402

EVAL = APP / "evals" / "rag-eval-10.jsonl"


async def run(k: int, limit: int, out: Path, revisions: int = 1, multi: bool = False):
    client = AsyncOpenAI(api_key=get_deepseek_key(), base_url="https://api.deepseek.com")
    questions = [json.loads(l) for l in EVAL.read_text(encoding="utf-8").splitlines() if l.strip()]
    if limit:
        questions = questions[:limit]

    rows, t_all = [], time.time()
    for q in questions:
        t0 = time.time()
        res = await pipeline.answer_verified(client, q["question"], k, max_revisions=revisions, multi_query=multi)
        v = res["verification"]
        rows.append({
            "id": q["id"],
            "question": q["question"],
            "answer": res["answer"],
            "sources": pipeline.format_sources(res["hits"]),
            "rounds": res["rounds"],
            "verdict": v.get("verdict"),
            "unsupported": v.get("unsupported") or [],
            "reason": v.get("reason"),
            "first_pass": v.get("first_pass"),
            "usage": res["usage"],
            "latency_ms": int((time.time() - t0) * 1000),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        })
        print(f"  {q['id']:>3}  verdict={v.get('verdict'):<6} rounds={res['rounds']} "
              f"unsupported={len(v.get('unsupported') or [])} "
              f"tokens={res['usage']['in']}/{res['usage']['out']} "
              f"{rows[-1]['latency_ms']}ms")

    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    tin = sum(r["usage"]["in"] for r in rows)
    tout = sum(r["usage"]["out"] for r in rows)
    rev = sum(1 for r in rows if r["rounds"] > 1)
    flagged = sum(1 for r in rows if r["verdict"] == "revise")
    print(f"\n{len(rows)} 题 · {time.time() - t_all:.1f}s")
    print(f"重写 {rev} 题 · 最终仍被标记 {flagged} 题 · tokens {tin}/{tout}")
    print(f"输出：{out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--revisions", type=int, default=1)
    ap.add_argument("--multi-query", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    dest = Path(args.out) if args.out else APP / "evals" / f"verify-{datetime.now():%Y%m%d}.jsonl"
    asyncio.run(run(args.k, args.limit, dest, args.revisions, args.multi_query))