"""W5-B：池内 rerank 选 top-k 块，再走与 run_baseline 相同的回答链路。

与 `rerank_eval.py` 的区别：那个只比文件级排序；这个直接跑答案，交给 judge.py 判分，
才能回答「rerank 选出的块能不能让模型答对」。

用法：
  python evals/rerank_answer_ab.py --eval evals/rag-eval-40.jsonl --out evals/rerank-ans-40.jsonl
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from openai import OpenAI  # noqa: E402

from credentials import get_deepseek_key  # noqa: E402
from rag.prompt import build_rag_messages  # noqa: E402
from rag.rag import retrieve  # noqa: E402

MODEL = "deepseek-chat"
TEMPERATURE = 0.0
MAX_TOKENS = 1024
RATES = {"in": 0.27 / 1e6, "out": 1.10 / 1e6}
MODEL_DIR = APP / "models" / "bge-reranker-base"
MODEL_NAME = "BAAI/bge-reranker-base"


def load_encoder():
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(model_name=MODEL_NAME, specific_model_path=str(MODEL_DIR), lazy_load=False)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", default=str(APP / "evals" / "rag-eval-40.jsonl"))
    ap.add_argument("--out", default=str(APP / "evals" / "rerank-ans-40.jsonl"))
    ap.add_argument("--pool", type=int, default=20)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    questions = [json.loads(line) for line in Path(args.eval).read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        questions = questions[: args.limit]

    encoder = load_encoder()
    client = OpenAI(api_key=get_deepseek_key(), base_url="https://api.deepseek.com")

    rows = []
    t_all = time.time()
    for q in questions:
        pool = retrieve(q["question"], args.pool)
        scores = [float(s) for s in encoder.rerank(q["question"], [h["text"] for h in pool], batch_size=len(pool))]
        order = sorted(range(len(pool)), key=lambda i: (-scores[i], i))
        hits = [pool[i] for i in order[: args.k]]

        msgs = build_rag_messages(q["question"], hits)
        t = time.time()
        try:
            r = client.chat.completions.create(
                model=MODEL, messages=msgs, temperature=TEMPERATURE, max_tokens=MAX_TOKENS
            )
            ans = r.choices[0].message.content or ""
            u = r.usage
            tin, tout = (u.prompt_tokens, u.completion_tokens) if u else (0, 0)
            err = None
        except Exception as e:  # noqa: BLE001
            ans, tin, tout, err = "", 0, 0, f"{type(e).__name__}: {e}"
        dt = int((time.time() - t) * 1000)

        retrieved, seen = [], set()
        for h in hits:
            if h["source"] not in seen:
                seen.add(h["source"])
                retrieved.append(h["source"])

        row = {
            "id": q["id"],
            "condition": "rerank",
            "model": MODEL,
            "answer": ans,
            "latency_ms": dt,
            "tokens_in": tin,
            "tokens_out": tout,
            "cost_usd": round(tin * RATES["in"] + tout * RATES["out"], 6),
            "retrieved": retrieved,
            "hit@3": None,
            "points_hit": None,
            "points_total": len(q["expected_points"]),
            "hallucination": None,
            "error": err,
        }
        rows.append(row)
        print(f"[rerank] {q['id']}  {dt}ms  in={tin} out={tout}  {'ERR ' + err if err else ''}")

    Path(args.out).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"\n完成：{len(rows)} 行 → {args.out}  用时 {time.time() - t_all:.0f}s")


if __name__ == "__main__":
    main()
