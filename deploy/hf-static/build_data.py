r"""从一次评测结果生成静态回放数据。

用法（在仓库根目录）：
    .\.venv\Scripts\python.exe deploy\hf-static\build_data.py
    .\.venv\Scripts\python.exe deploy\hf-static\build_data.py --src evals\verify-multi-k10-20261026.jsonl
"""

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DEFAULT_SRC = ROOT / "evals" / "verify-multi-k10-20261026.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(DEFAULT_SRC))
    ap.add_argument("--out", default=str(HERE / "data.json"))
    args = ap.parse_args()

    src = Path(args.src)
    items = []
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        items.append({
            "id": r["id"],
            "question": r["question"],
            "answer": r["answer"],
            "sources": r.get("sources") or [],
            "verification": {
                "verdict": r.get("verdict"),
                "unsupported": r.get("unsupported") or [],
                "reason": r.get("reason") or "",
            },
            "usage": r.get("usage") or {},
            "rounds": r.get("rounds", 1),
            "timestamp": r.get("timestamp"),
        })

    meta = {
        "model": "deepseek-chat",
        "k": 10,
        "multi_query": True,
        "max_revisions": 0,
        "run_date": items[0]["timestamp"][:10] if items and items[0].get("timestamp") else "",
        "repo": "https://github.com/Aozak1Aok0/todo-rag",
        "note": "静态回放：答案与引用来自真实运行（本地检索 + DeepSeek）。线上页面不调用模型。",
    }
    Path(args.out).write_text(
        json.dumps({"meta": meta, "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"wrote {args.out} ({len(items)} items)")


if __name__ == "__main__":
    main()
