"""baseline 运行器（条件① 无上下文 / 条件② 全文塞进 prompt）。

职责边界（重要）：
    只做「跑题 + 存档」——调用模型、拿原始回答、记耗时与 token 数。
    打分层的四个字段（retrieved / hit@3 / points_hit / hallucination）一律写 None，
    由你自己的 scorer 去填。
    依据 evals/rag-eval-10.md 的约定：打分脚本你自己写。

用法（在 fastapi-api 目录下）：
    PowerShell:
        $env:DEEPSEEK_API_KEY="sk-xxxx"
        .\\.venv\\Scripts\\python.exe evals\\run_baseline.py
    只跑某几个条件 / 试跑 / 只跑某几题：
        ... run_baseline.py --conditions noctx
        ... run_baseline.py --limit 1
        ... run_baseline.py --question Q1,Q9
        ... run_baseline.py --out evals/baseline-try.jsonl
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from openai import OpenAI

HERE = Path(__file__).resolve().parent          # evals/
APP = HERE.parent                                # fastapi-api/
PRA = APP.parent.parent                          # pra/
if str(APP) not in sys.path:                      # 让 rag/ 可导入
    sys.path.insert(0, str(APP))

from rag.prompt import build_rag_messages  # noqa: E402
DEFAULT_EVAL = HERE / "rag-eval-10.jsonl"
DEFAULT_CORPUS = HERE / "corpus.txt"

MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
TEMPERATURE = 0.0            # 固定 0，baseline 才可复现
MAX_TOKENS = 1024
RAG_K = int(os.getenv("RAG_K", "5"))   # 条件③ 检索多少块（可用环境变量调，便于 A/B）
RAG_PROMPT = os.getenv("RAG_PROMPT", "C")  # 条件③ 提示词变体（A/B/C；C=只纠标识符）

# 单价（每百万 token）。按你账单口径填；留 0 表示本次不计成本。
RATES = {"in": 0.0, "out": 0.0}

SYSTEM = "你是这个项目的代码库问答助手。请准确、简洁地用中文回答。"


def load_corpus(manifest: Path):
    files = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        files.append(s)
    parts, missing = [], []
    for rel in files:
        p = PRA / rel
        if p.is_file():
            body = p.read_text(encoding="utf-8", errors="replace")
            parts.append(f"# ==== {rel} ====\n{body}")
        else:
            missing.append(rel)
    return "\n\n".join(parts), missing


def load_questions(path: Path):
    qs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            qs.append(json.loads(line))
    return qs


def build_messages(condition: str, question: str, corpus: str):
    if condition == "noctx":
        return [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ]
    if condition == "fullctx":
        user = (
            "以下是与本项目相关的资料：\n\n"
            f"{corpus}\n\n"
            "---\n"
            "请仅根据上面的资料回答问题；资料里没有的，请明确说明「资料中没有」，不要编造。\n\n"
            f"问题：{question}"
        )
        return [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ]
    raise ValueError(f"未知条件: {condition}")


def git(*args: str) -> str:
    try:
        r = subprocess.run(
            ["git", "-C", str(PRA), *args],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip()
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", default=str(DEFAULT_EVAL))
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS))
    ap.add_argument("--conditions", default="noctx,fullctx,rag")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--question", default="", help="只跑指定 id，逗号分隔，如 Q1,Q9")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        try:
            from credentials import get_deepseek_key
            key = get_deepseek_key()
        except Exception:  # noqa: BLE001
            key = None
    if not key:
        print("[x] 未找到 DeepSeek key：设置 DEEPSEEK_API_KEY，或创建 Windows 凭据 WorkBuddy/DeepSeek。")
        sys.exit(1)
    client = OpenAI(api_key=key, base_url=BASE_URL)

    questions = load_questions(Path(args.eval))
    if args.question:
        want = {x.strip() for x in args.question.split(",") if x.strip()}
        questions = [q for q in questions if q["id"] in want]
    if args.limit:
        questions = questions[: args.limit]

    corpus, missing = load_corpus(Path(args.corpus))
    conds = [c.strip() for c in args.conditions.split(",") if c.strip()]

    commit = git("rev-parse", "--short", "HEAD") or "nogit"
    stamp = datetime.now().strftime("%Y%m%d")
    if not args.out:
        args.out = str(HERE / f"baseline-{commit}-{stamp}.jsonl")

    print(f"语料：{len(corpus)} 字符" + (f"  缺失: {missing}" if missing else ""))
    print(f"题目：{len(questions)} 题 × 条件 {conds}")
    print(f"模型：{MODEL} (temp={TEMPERATURE}, max_tokens={MAX_TOKENS})")
    print(f"输出：{args.out}\n")

    if "rag" in conds:
        from rag.rag import retrieve  # 只有跑条件③才加载向量模型

    rows, t0 = [], time.time()
    for cond in conds:
        for q in questions:
            retrieved = None
            if cond == "rag":
                hits = retrieve(q["question"], RAG_K)
                msgs = build_rag_messages(q["question"], hits, RAG_PROMPT)
                retrieved = []
                for h in hits:
                    if h["source"] not in retrieved:
                        retrieved.append(h["source"])
            else:
                msgs = build_messages(cond, q["question"], corpus)
            t = time.time()
            try:
                r = client.chat.completions.create(
                    model=MODEL,
                    messages=msgs,
                    temperature=TEMPERATURE,
                    max_tokens=MAX_TOKENS,
                )
                ans = r.choices[0].message.content or ""
                u = r.usage
                tin = u.prompt_tokens if u else 0
                tout = u.completion_tokens if u else 0
                err = None
            except Exception as e:  # noqa: BLE001
                ans, tin, tout, err = "", 0, 0, f"{type(e).__name__}: {e}"
            dt = int((time.time() - t) * 1000)
            cost = round(tin / 1e6 * RATES["in"] + tout / 1e6 * RATES["out"], 6)
            rows.append({
                "id": q["id"],
                "condition": cond,
                "model": MODEL,
                "answer": ans,
                "latency_ms": dt,
                "tokens_in": tin,
                "tokens_out": tout,
                "cost_usd": cost,
                # ↓↓↓ 打分层：留 None，由你自己的 scorer 填 ↓↓↓
                "retrieved": retrieved,
                "hit@3": None,
                "points_hit": None,
                "points_total": len(q.get("expected_points", [])),
                "hallucination": None,
                # ↑↑↑ 打分层 ↑↑↑
                "error": err,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            })
            flag = "ERR" if err else "ok"
            print(f"  [{cond:7}] {q['id']:>3}  {flag:3}  {dt:>5}ms  in={tin} out={tout}  {err or ''}")

    out = Path(args.out)
    out.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )

    man = {
        "commit": commit,
        "branch": git("branch", "--show-current"),
        "time": datetime.now().isoformat(timespec="seconds"),
        "model": MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "conditions": conds,
        "questions": [q["id"] for q in questions],
        "eval_version": sorted({q.get("eval_version", "?") for q in questions}),
        "rag_prompt": RAG_PROMPT,
        "corpus_chars": len(corpus),
        "corpus_manifest": str(DEFAULT_CORPUS),
        "rows": len(rows),
        "elapsed_s": round(time.time() - t0, 1),
    }
    man_path = out.with_suffix(".manifest.json")
    man_path.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n完成：{len(rows)} 行 → {out}")
    print(f"清单：{man_path}")
    print("提醒：retrieved / hit@3 / points_hit / hallucination 仍为 null，等你的 scorer 填。")


if __name__ == "__main__":
    main()
