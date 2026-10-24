"""把 baseline / RAG 结果 JSONL 排版成便于人工阅读的 Markdown。

⚠️ 纯展示器：不做任何打分、不算 points_hit、不判 hallucination。
    打分层的四个字段是 None 还是你自己填 —— 按 evals/rag-eval-10.md 的约定，打分脚本你自己写。
    这里只把「问题 + 你的打分锚点 + 各条件的原始回答」摆在一起，省得你对着 JSONL 一行行看。

用法：
    python evals/render_answers.py --in evals/baseline-218e53a-20261016.jsonl
    python evals/render_answers.py --in evals/rag-run.jsonl --out evals/rag-run.md
"""

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_EVAL = HERE / "rag-eval-10.jsonl"

COND_LABEL = {
    "noctx": "条件① 无上下文（纯靠模型记忆）",
    "fullctx": "条件② 全文塞进 prompt（上限）",
    "rag": "条件③ RAG 检索后回答",
}


def load_jsonl(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--eval", default=str(DEFAULT_EVAL))
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    src = Path(args.inp)
    out = Path(args.out) if args.out else src.with_suffix(".md")

    rows = load_jsonl(src)
    questions = {q["id"]: q for q in load_jsonl(Path(args.eval))}
    order = []
    by_id = {}
    for r in rows:
        qid = r["id"]
        if qid not in by_id:
            by_id[qid] = {}
            order.append(qid)
        by_id[qid][r["condition"]] = r

    lines = []
    lines.append(f"# 回答阅读稿：{src.name}\n")
    man = src.with_suffix(".manifest.json")
    if man.is_file():
        m = json.loads(man.read_text(encoding="utf-8"))
        lines.append(
            f"> commit `{m.get('commit')}` · 分支 `{m.get('branch')}` · 模型 `{m.get('model')}` "
            f"temp={m.get('temperature')} · 条件 {m.get('conditions')} · 生成于 {m.get('time')}\n"
        )
    lines.append("> 本文件仅供阅读；打分层字段请你在 scorer 里填。\n")
    lines.append("---\n")

    for qid in order:
        q = questions.get(qid, {})
        lines.append(f"## {qid} · {q.get('type','?')} · 难度 {q.get('difficulty','?')}\n")
        lines.append(f"**问题**：{q.get('question','(缺)')}\n")
        pts = q.get("expected_points", [])
        if pts:
            lines.append("**你的打分锚点（expected_points）**：")
            for i, p in enumerate(pts, 1):
                lines.append(f"- {i}. {p}")
            lines.append("")
        gold = q.get("gold_sources", [])
        if gold:
            lines.append(f"**gold_sources**：{'、'.join(gold)}"
                         + ("  ·  **本题必须拒答**" if q.get("must_refuse") else "") + "\n")
        if q.get("notes"):
            lines.append(f"**判分说明**：{q['notes']}\n")

        for cond, r in by_id[qid].items():
            label = COND_LABEL.get(cond, cond)
            stat = (f"`{r.get('latency_ms')}ms` · in={r.get('tokens_in')} "
                    f"out={r.get('tokens_out')} · err={r.get('error')}")
            lines.append(f"### {label}  <sub>{stat}</sub>\n")
            ans = (r.get("answer") or "").strip()
            lines.append(ans if ans else "_（空回答）_")
            lines.append("")
        lines.append("---\n")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"已生成：{out}  （{len(order)} 题）")


if __name__ == "__main__":
    main()
