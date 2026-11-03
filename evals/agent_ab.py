r"""单 Agent vs 多 Agent 对照：跑两套评测，生成可复现的对照表。

用法：
    .\\.venv\\Scripts\\python.exe evals\\agent_ab.py
"""

import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="agent-ab-"))


def _run(script, out):
    cmd = [sys.executable, str(APP / "evals" / script), "--out", str(out)]
    subprocess.run(cmd, cwd=str(APP), check=True)


def _load(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main():
    single_out = TMP / "single.jsonl"
    multi_out = TMP / "multi.jsonl"
    _run("single_agent_eval.py", single_out)
    _run("multi_agent_eval.py", multi_out)

    single = {r["id"]: r for r in _load(single_out)}
    multi = {r["id"]: r for r in _load(multi_out)}
    ids = [i for i in single if i in multi]

    lines = [
        "# 单 Agent vs 多 Agent（同一批 8 个用例）",
        "",
        f"- 时间：{datetime.now():%Y-%m-%d %H:%M}",
        "- 单 Agent：`agents/single.py`，一个模型 + 全部工具，无显式路由",
        "- 多 Agent：`agents/orchestrator.py`，Supervisor + Todo/Docs specialist",
        "",
        "| 用例 | 单 Agent | 多 Agent | 单 tokens in/out | 多 tokens in/out | 单延迟 | 多延迟 |",
        "|---|---|---|---|---|---|---|",
    ]
    s_pass = m_pass = 0
    s_tin = s_tout = m_tin = m_tout = 0
    s_lat = m_lat = 0
    for i in ids:
        s, m = single[i], multi[i]
        ok_s, ok_m = bool(s.get("ok")), bool(m.get("ok"))
        s_pass += ok_s
        m_pass += ok_m
        s_tin += s["usage"]["in"]
        s_tout += s["usage"]["out"]
        m_tin += m["usage"]["in"]
        m_tout += m["usage"]["out"]
        s_lat += s["latency_ms"]
        m_lat += m["latency_ms"]
        lines.append(
            f"| {i} | {'PASS' if ok_s else 'FAIL'} | {'PASS' if ok_m else 'FAIL'} "
            f"| {s['usage']['in']}/{s['usage']['out']} | {m['usage']['in']}/{m['usage']['out']} "
            f"| {s['latency_ms']}ms | {m['latency_ms']}ms |"
        )

    n = len(ids) or 1
    lines += [
        "",
        "## 汇总",
        "",
        "| 指标 | 单 Agent | 多 Agent |",
        "|---|---|---|",
        f"| 通过 | {s_pass}/{len(ids)} | {m_pass}/{len(ids)} |",
        f"| tokens in/out | {s_tin}/{s_tout} | {m_tin}/{m_tout} |",
        f"| 平均延迟 | {s_lat // n}ms | {m_lat // n}ms |",
    ]

    md = "\n".join(lines) + "\n"
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    dest = APP / "evals" / f"agent-ab-{stamp}.md"
    dest.write_text(md, encoding="utf-8")
    merged = APP / "evals" / f"agent-ab-{stamp}.jsonl"
    merged.write_text(
        "\n".join(
            json.dumps({"id": i, "single": single[i], "multi": multi[i]}, ensure_ascii=False)
            for i in ids
        )
        + "\n",
        encoding="utf-8",
    )
    print(md)
    print(f"已写入：{dest} / {merged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
