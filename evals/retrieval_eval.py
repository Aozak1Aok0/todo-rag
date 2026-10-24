r"""检索层评测：只测召回，不调大模型（不花钱、秒级）。

指标（对应 rag-eval-10.md 第 3 节）：
    hit@1 / hit@3 / hit@5 —— top-k 里是否出现 gold_sources 里的文件
    MRR                    —— 第一个命中位置的倒数均值

说明：gold 是**文件级**标注，所以名次按「文件去重后的顺序」算
（同一文件的不同块不重复占位），这样 hit@3 才反映"能不能找到对的文件"。

用法（在 fastapi-api 目录下）：
    .\.venv\Scripts\python.exe evals\retrieval_eval.py
    .\.venv\Scripts\python.exe evals\retrieval_eval.py --k 8
"""

import argparse
import json
import sys
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


def norm_gold(s: str) -> str:
    # gold 里是 pra/xxx（相对仓库根），索引里是 xxx（相对 pra/）
    return s[4:] if s.startswith("pra/") else s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    questions = [json.loads(l) for l in EVAL.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = []
    rr_sum = 0.0

    for q in questions:
        gold = {norm_gold(s) for s in q["gold_sources"]}
        hits = retrieve(q["question"], args.k)

        # 文件级去重，保留首次出现的顺序
        seen, uniq = set(), []
        for h in hits:
            if h["source"] not in seen:
                seen.add(h["source"])
                uniq.append(h["source"])

        rank = next((i + 1 for i, s in enumerate(uniq) if s in gold), None)
        rr_sum += (1.0 / rank) if rank else 0.0
        rows.append((q["id"], rank, uniq, gold))

    def hit(k):
        return sum(1 for _, r, _, _ in rows if r and r <= k)

    n = len(rows)
    print(f"\n检索评测：{n} 题 · top-{args.k} 块 · 文件级名次 · 集合 pra_corpus\n")
    print(f"{'题':<4} {'名次':<6} {'gold 文件':<40} top-{args.k} 召回文件")
    print("-" * 118)
    for qid, rank, uniq, gold in rows:
        r = f"#{rank}" if rank else "MISS"
        g = ", ".join(sorted(x.split("/")[-1] for x in gold))
        got = " | ".join(s.split("/")[-1] for s in uniq)
        print(f"{qid:<4} {r:<6} {g:<40} {got}")

    print("-" * 118)
    print(f"hit@1 = {hit(1)}/{n}   hit@3 = {hit(3)}/{n}   hit@{args.k} = {hit(args.k)}/{n}")
    print(f"MRR   = {rr_sum / n:.3f}")
    miss = [qid for qid, rank, _, _ in rows if not rank]
    if miss:
        print(f"完全没召回的题：{', '.join(miss)}")
        print("-> 先调分块（CHUNK_LINES / OVERLAP）或 k；仍不行再检查 gold 是否写错")


if __name__ == "__main__":
    main()