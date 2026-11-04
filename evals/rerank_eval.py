r"""rerank 评测：在固定候选池上比较「不 rerank」与「cross-encoder rerank」。

为什么先固定候选池：生产链路是「向量 top20 + BM25 top20 → RRF → top-k」。
rerank 只能重排池子里已有的块，池子里没有的它救不回来。所以先钉住池子、只换排序器，
才能把「召回不够」和「排序不好」分开——否则提升/下降都说不清是谁的功劳。

指标与 retrieval_eval.py 对齐（文件级去重）：hit@1/3/5、MRR；另加 nDCG@5 与延迟分位数。
gold 是文件级标注，同一文件的多个块不重复占位，这样 hit@3 才反映「能不能找到对的文件」。

两个变体：
    base   —— 生产 retrieve() 返回的顺序（含两条规则）
    rerank —— 同一个池子，用 cross-encoder 逐条打分后重排（纯排序，不还原规则）

用法（在 fastapi-api 目录下）：
    .\\.venv\\Scripts\\python.exe evals\\rerank_eval.py
    .\\.venv\\Scripts\\python.exe evals\\rerank_eval.py --pool 20 --k 5
    .\\.venv\\Scripts\\python.exe evals\\rerank_eval.py --no-rerank   # 只校验基线可复现，不加载模型

模型约 1.04GB（已 gitignore），放在 models/bge-reranker-base/；缺失时按提示用 hf-mirror 下载。
"""

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

APP = Path(__file__).resolve().parent.parent
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from rag.rag import retrieve  # noqa: E402

EVAL = APP / "evals" / "rag-eval-10.jsonl"
MODEL_NAME = "BAAI/bge-reranker-base"
MODEL_DIR = APP / "models" / "bge-reranker-base"


def norm_gold(s: str) -> str:
    # gold 里是 pra/xxx（相对仓库根），索引里是 xxx（相对 pra/）
    return s[4:] if s.startswith("pra/") else s


def file_order(hits):
    """按文件去重，保留首次出现的顺序。"""
    seen, out = set(), []
    for h in hits:
        if h["source"] not in seen:
            seen.add(h["source"])
            out.append(h["source"])
    return out


def rank_of(order, gold):
    return next((i + 1 for i, s in enumerate(order) if s in gold), None)


def chunk_rank(hits, gold):
    """块级名次（不按文件去重）：rerank 主要在文件内部重排，这个指标才敏感。"""
    return next((i + 1 for i, h in enumerate(hits) if h["source"] in gold), None)


def ndcg_at(order, gold, k):
    """文件级二值相关性 nDCG@k；IDCG 按「理想情况下前 |gold| 个都命中」算。"""
    dcg = sum(1.0 / math.log2(i + 2) for i, s in enumerate(order[:k]) if s in gold)
    ideal_n = min(len(gold), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_n))
    return dcg / idcg if idcg else 0.0


def pct(xs, p):
    if not xs:
        return 0.0
    s = sorted(xs)
    idx = min(len(s) - 1, max(0, int(round(p / 100 * (len(s) - 1)))))
    return s[idx]


def load_questions(path: Path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_encoder(model_name: str, model_dir: Path):
    """加载 cross-encoder；显式指定本地目录，绕开 hub 快照的符号链接问题（同 embed.py）。"""
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    if not (model_dir / "onnx" / "model.onnx").is_file():
        raise FileNotFoundError(
            f"本地 reranker 模型不存在：{model_dir}\n"
            "下载（国内用 hf-mirror）：\n"
            "  mkdir -p models/bge-reranker-base/onnx\n"
            "  for f in config.json tokenizer.json tokenizer_config.json special_tokens_map.json vocab.txt; do\n"
            '    curl -sL --fail "https://hf-mirror.com/BAAI/bge-reranker-base/resolve/main/$f" -o "models/bge-reranker-base/$f"\n'
            "  done\n"
            '  curl -sL --fail "https://hf-mirror.com/BAAI/bge-reranker-base/resolve/main/onnx/model.onnx" -o models/bge-reranker-base/onnx/model.onnx\n'
        )
    return TextCrossEncoder(
        model_name=model_name,
        specific_model_path=str(model_dir),
        lazy_load=False,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", default=str(EVAL))
    ap.add_argument("--k", type=int, default=5, help="最终取前几块（指标按文件级名次算）")
    ap.add_argument("--pool", type=int, default=20, help="候选池大小，必须 >= k")
    ap.add_argument("--model", default=MODEL_NAME)
    ap.add_argument("--model-dir", default=str(MODEL_DIR))
    ap.add_argument("--no-rerank", action="store_true", help="只跑 base 变体，用于校验基线")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="", help="输出前缀，默认 evals/rerank-<stamp>")
    args = ap.parse_args()

    if args.pool < args.k:
        print(f"[x] --pool({args.pool}) 必须 >= --k({args.k})")
        sys.exit(2)

    questions = load_questions(Path(args.eval))
    if args.limit:
        questions = questions[: args.limit]

    tag = datetime.now().strftime("%Y%m%d-%H%M")
    out_prefix = Path(args.out) if args.out else APP / "evals" / f"rerank-{tag}"
    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    encoder = None
    if not args.no_rerank:
        try:
            encoder = load_encoder(args.model, Path(args.model_dir))
        except Exception as e:  # noqa: BLE001
            print(f"[x] {e}")
            sys.exit(2)

    print(f"\nrerank 评测：{len(questions)} 题 · 池 {args.pool} · top-{args.k} · 模型 {args.model}")
    print(f"输出：{out_prefix}.jsonl / .md\n")

    rows, base_ms, rerank_ms = [], [], []
    base_rows, rr_rows = [], []

    for q in questions:
        gold = {norm_gold(s) for s in q["gold_sources"]}

        t0 = time.perf_counter()
        pool = retrieve(q["question"], args.pool)
        base_ms.append((time.perf_counter() - t0) * 1000)

        base_order = file_order(pool)
        base_rank = rank_of(base_order, gold)
        base_chunk = chunk_rank(pool, gold)

        if encoder is not None:
            t1 = time.perf_counter()
            scores = [float(s) for s in encoder.rerank(q["question"], [h["text"] for h in pool], batch_size=args.pool)]
            rerank_ms.append((time.perf_counter() - t1) * 1000)
            order = sorted(range(len(pool)), key=lambda i: (-scores[i], i))
            reranked_hits = [pool[i] for i in order]
            rerank_order = file_order(reranked_hits)
            rerank_rank = rank_of(rerank_order, gold)
            rerank_chunk = chunk_rank(reranked_hits, gold)
        else:
            scores, rerank_order, rerank_rank = [], base_order, base_rank
            reranked_hits, rerank_chunk = pool, base_chunk

        base_rows.append({"id": q["id"], "variant": "base", "rank": base_rank,
                          "chunk_rank": base_chunk,
                          "order": base_order, "ndcg@5": ndcg_at(base_order, gold, args.k)})
        rr_rows.append({"id": q["id"], "variant": "rerank", "rank": rerank_rank,
                        "chunk_rank": rerank_chunk,
                        "order": rerank_order, "ndcg@5": ndcg_at(rerank_order, gold, args.k)})
        rows.append({
            "id": q["id"],
            "question": q["question"],
            "gold_sources": sorted(gold),
            "pool_ids": [h["id"] for h in pool],
            "pool_sources": file_order(pool),
            "scores": scores,
            "base_order": base_order,
            "rerank_order": rerank_order,
            "base_chunk_rank": base_chunk,
            "rerank_chunk_rank": rerank_chunk,
        })

        def fmt(r):
            return f"#{r}" if r else "MISS"

        print(f"{q['id']:<4} base {fmt(base_rank):<6} rerank {fmt(rerank_rank):<6} "
              f"gold={', '.join(sorted(x.split('/')[-1] for x in gold))}")

    def summarize(rows_):
        n = len(rows_)
        ranks = [r["rank"] for r in rows_]
        chunks = [r["chunk_rank"] for r in rows_]
        return {
            "n": n,
            "hit@1": sum(1 for r in ranks if r and r <= 1),
            "hit@3": sum(1 for r in ranks if r and r <= 3),
            f"hit@{args.k}": sum(1 for r in ranks if r and r <= args.k),
            "mrr": round(sum(1.0 / r for r in ranks if r) / n, 3),
            "ndcg@5": round(sum(r["ndcg@5"] for r in rows_) / n, 3),
            "chunk@1": sum(1 for c in chunks if c and c <= 1),
            "chunk@3": sum(1 for c in chunks if c and c <= 3),
            "chunk_mrr": round(sum(1.0 / c for c in chunks if c) / n, 3),
        }

    s_base = summarize(base_rows)
    s_rr = summarize(rr_rows)

    print("-" * 78)
    print(f"{'指标':<10} {'base':<12} {'rerank':<12} {'Δ'}")
    for key in ["hit@1", "hit@3", f"hit@{args.k}", "mrr", "ndcg@5", "chunk@1", "chunk@3", "chunk_mrr"]:
        d = s_rr[key] - s_base[key]
        print(f"{key:<10} {str(s_base[key]):<12} {str(s_rr[key]):<12} {d:+.3f}")
    if rerank_ms:
        print(f"\n延迟  retrieve p50/p95 = {pct(base_ms, 50):.0f}/{pct(base_ms, 95):.0f} ms"
              f" · rerank p50/p95 = {pct(rerank_ms, 50):.0f}/{pct(rerank_ms, 95):.0f} ms")

    # ---- 落盘 ----
    with (Path(str(out_prefix) + ".jsonl")).open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    md = [f"# rerank 评测 {tag}", "",
          f"- 池：{args.pool} · top-{args.k} · 题数：{len(questions)} · 模型：`{args.model}`",
          "- 变体：base（生产顺序）vs rerank（纯排序，不还原点名文件的置顶规则）", "",
          "| 指标 | base | rerank | Δ |", "|---|---|---|---|"]
    for key in ["hit@1", "hit@3", f"hit@{args.k}", "mrr", "ndcg@5", "chunk@1", "chunk@3", "chunk_mrr"]:
        md.append(f"| {key} | {s_base[key]} | {s_rr[key]} | {s_rr[key] - s_base[key]:+.3f} |")
    if rerank_ms:
        md += ["", f"延迟：retrieve p50/p95 = {pct(base_ms, 50):.0f}/{pct(base_ms, 95):.0f} ms；"
                   f"rerank p50/p95 = {pct(rerank_ms, 50):.0f}/{pct(rerank_ms, 95):.0f} ms"]
    md += ["", "## 逐题", "", "| 题 | base 名次 | rerank 名次 | base top5 | rerank top5 |", "|---|---|---|---|---|"]
    for b, r in zip(base_rows, rr_rows):
        md.append(f"| {b['id']} | {b['rank'] or 'MISS'} | {r['rank'] or 'MISS'} | "
                  f"{', '.join(x.split('/')[-1] for x in b['order'][:args.k])} | "
                  f"{', '.join(x.split('/')[-1] for x in r['order'][:args.k])} |")
    Path(str(out_prefix) + ".md").write_text("\n".join(md) + "\n", encoding="utf-8")

    manifest = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "model": args.model,
        "pool": args.pool,
        "k": args.k,
        "questions": [q["id"] for q in questions],
        "eval_file": str(Path(args.eval)),
        "rows": len(rows),
        "base": s_base,
        "rerank": s_rr,
        "latency_ms": {
            "retrieve_p50": round(pct(base_ms, 50), 1),
            "retrieve_p95": round(pct(base_ms, 95), 1),
            "rerank_p50": round(pct(rerank_ms, 50), 1) if rerank_ms else None,
            "rerank_p95": round(pct(rerank_ms, 95), 1) if rerank_ms else None,
        },
    }
    if not args.no_rerank:
        manifest["model_dir"] = str(Path(args.model_dir))
    Path(str(out_prefix) + ".manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n已写入：{out_prefix}.jsonl / .md / .manifest.json")


if __name__ == "__main__":
    main()
