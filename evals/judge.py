"""LLM 判分器：用 expected_points 给答案打分，可对旧的人工标注做校准。

用法：
  .\\.venv\\Scripts\\python.exe evals\\judge.py --answers evals\\rag-current-20261024.jsonl
  .\\.venv\\Scripts\\python.exe evals\\judge.py --answers <40 题结果> --eval evals\\rag-eval-40.jsonl

输出：
  evals/judge-<stamp>.jsonl   每题 hit/miss/hallucinated + judge 原文
  evals/judge-<stamp>.md      汇总、与人工标注的一致率（答案文件里带 points_hit 时）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DEFAULT_EVAL = ROOT / "evals" / "rag-eval-40.jsonl"

SYSTEM = """你是严格的 RAG 答案评分员。只依据给定的「期望要点」判断答案是否命中，不因为答案更长、更礼貌而加分。

规则：
1. 逐条判断每个期望要点是否在答案中被**明确表达**（同义表述算命中，含糊暗示不算）。
2. hallucinated 只记「与语料摘录直接矛盾」的具体断言，并附上摘录中的原文片段作为证据；摘录里找不到、但也不矛盾的断言记入 unverified，不算幻觉（摘录可能被截断）。
3. 若 must_refuse 为 true：答案必须明确表示「语料中没有/未说明」，并编造具体实现即算 hallucination。
4. 若答案明确表示「资料中没有 / 无法确认 / 未给出」，该要点判为未命中（哪怕这个判断本身是对的）——评分看的是「说出来了没有」，不是「有没有诚实承认不知道」。
5. 只输出 JSON，不要解释之外的内容。

输出格式：
{"hit": [命中的要点编号], "miss": [未命中的编号], "hallucinated": ["与摘录矛盾的断言 + 摘录原文"], "unverified": ["摘录中找不到但也不矛盾的断言"], "note": "一句话理由"}"""


def _key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY")
    if key:
        return key
    try:
        from credentials import get_deepseek_key

        key = get_deepseek_key()
    except Exception:  # noqa: BLE001
        key = None
    if not key:
        raise SystemExit("未找到 DeepSeek key：设置 DEEPSEEK_API_KEY，或创建 Windows 凭据 WorkBuddy/DeepSeek")
    return key


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_context(q: dict, corpus: Path, truncate: int, budget: int, retrieved: list[str] | None = None) -> str:
    paths: list[str] = list(q.get("gold_sources") or []) + list(retrieved or [])
    parts: list[str] = []
    seen: set[str] = set()
    used = 0
    for src in paths:
        rel = src[4:] if src.startswith("pra/") else src
        p = corpus / rel
        if rel in seen or not p.exists() or used >= budget:
            continue
        seen.add(rel)
        text = p.read_text(encoding="utf-8", errors="ignore")[:truncate]
        block = f"--- {rel} ---\n{text}"
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)[:budget]


async def judge_one(client: AsyncOpenAI, q: dict, answer: str, context: str) -> dict:
    points = q["expected_points"]
    payload = {
        "question": q["question"],
        "expected_points": {str(i + 1): p for i, p in enumerate(points)},
        "must_refuse": bool(q.get("must_refuse")),
        "answer": answer,
    }
    if context:
        payload["corpus_excerpt"] = context
    user = json.dumps(payload, ensure_ascii=False)
    for attempt in range(2):
        try:
            resp = await client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or "{}"
            data = json.loads(raw)
            hit = [int(x) for x in data.get("hit") or [] if str(x).isdigit() and 1 <= int(x) <= len(points)]
            return {
                "hit": sorted(set(hit)),
                "miss": sorted(set(range(1, len(points) + 1)) - set(hit)),
                "hallucinated": data.get("hallucinated") or [],
                "unverified": data.get("unverified") or [],
                "note": data.get("note", ""),
                "raw": raw,
            }
        except Exception as e:  # noqa: BLE001
            if attempt == 1:
                return {"hit": [], "miss": list(range(1, len(points) + 1)), "hallucinated": [], "note": f"judge error: {type(e).__name__}", "raw": ""}
            await asyncio.sleep(2)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", default=str(DEFAULT_EVAL))
    ap.add_argument("--answers", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--corpus", default=str(ROOT / "corpus"))
    ap.add_argument("--no-context", action="store_true", help="不把 gold_sources 摘录给判分器")
    ap.add_argument("--truncate", type=int, default=30000, help="单个语料文件最多截取字符数")
    ap.add_argument("--max-context", type=int, default=60000, help="每题语料摘录总字符上限")
    args = ap.parse_args()

    evalset = {q["id"]: q for q in load_jsonl(Path(args.eval))}
    answers = [a for a in load_jsonl(Path(args.answers)) if a.get("answer")]
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out_jsonl = Path(args.out) if args.out else ROOT / "evals" / f"judge-{stamp}.jsonl"

    client = AsyncOpenAI(api_key=_key(), base_url="https://api.deepseek.com")
    sem = asyncio.Semaphore(max(1, args.concurrency))
    results: list[dict] = []

    async def run(a: dict) -> None:
        q = evalset.get(a["id"])
        if not q:
            return
        async with sem:
            retrieved = a.get("retrieved") if isinstance(a.get("retrieved"), list) else []
            ctx = "" if args.no_context else build_context(q, Path(args.corpus), args.truncate, args.max_context, retrieved)
            v = await judge_one(client, q, a["answer"], ctx)
        results.append(
            {
                "id": a["id"],
                "condition": a.get("condition"),
                "split": q.get("split"),
                "points_total": len(q["expected_points"]),
                "points_hit": len(v["hit"]),
                "hallucination": bool(v["hallucinated"]),
                "hit": v["hit"],
                "miss": v["miss"],
                "hallucinated": v["hallucinated"],
                "unverified": v.get("unverified") or [],
                "note": v["note"],
                "manual_hit": a.get("points_hit"),
                "manual_hallucination": a.get("hallucination"),
            }
        )

    await asyncio.gather(*(run(a) for a in answers))
    results.sort(key=lambda r: (int(r["id"][1:]), r.get("condition") or ""))

    out_jsonl.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n", encoding="utf-8")

    judged = [r for r in results if not r["note"].startswith("judge error")]
    total = sum(r["points_total"] for r in judged)
    hit = sum(r["points_hit"] for r in judged)
    halluc = sum(1 for r in judged if r["hallucination"])
    paired = [r for r in results if r.get("manual_hit") not in (None, "None")]
    agree = sum(1 for r in paired if int(r["manual_hit"]) == r["points_hit"])
    halluc_agree = sum(1 for r in paired if bool(r["manual_hallucination"]) == r["hallucination"])

    lines = [
        f"# LLM 判分 {stamp}",
        "",
        f"- 答案文件：`{Path(args.answers).name}` · 题数 {len(results)}（有效 {len(judged)}）",
        f"- 要点命中 **{hit}/{total}**（{hit / total * 100:.1f}%）· 幻觉 {halluc} 题",
    ]
    if paired:
        lines += [
            f"- 与人工标注一致：要点 **{agree}/{len(paired)}**（{agree / len(paired) * 100:.0f}%）· 幻觉判定 **{halluc_agree}/{len(paired)}**",
            "",
            "| 题 | 人工 | judge | 差异 |",
            "|---|---|---|---|",
        ]
        for r in paired:
            diff = int(r["manual_hit"]) - r["points_hit"]
            lines.append(f"| {r['id']} | {r['manual_hit']}/{r['points_total']} | {r['points_hit']}/{r['points_total']} | {diff:+d} |")
    lines += ["", "| 题 | 命中 | 未命中编号 | 幻觉 | 备注 |", "|---|---|---|---|---|"]
    for r in judged:
        lines.append(
            f"| {r['id']} | {r['points_hit']}/{r['points_total']} | {','.join(map(str, r['miss'])) or '-'} | "
            f"{'是' if r['hallucination'] else '否'} | {str(r['note'])[:60]} |"
        )
    out_md = out_jsonl.with_suffix(".md")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"题数 {len(results)} · 要点 {hit}/{total} · 幻觉 {halluc} · 一致 {agree}/{len(paired)}")
    print(f"已写入：{out_jsonl}\n        {out_md}")


if __name__ == "__main__":
    asyncio.run(main())
