r"""观测冒烟：/rag 打点 → /stats 汇总。

用临时 OBS_DIR，不碰真实 logs/。
"""

import os
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="obs-smoke-"))
os.environ["OBS_DIR"] = str(TMP / "logs")
os.environ["TODO_DB"] = str(TMP / "todos.db")

sys.path.insert(0, str(APP))
from credentials import get_deepseek_key  # noqa: E402

os.environ["DEEPSEEK_API_KEY"] = get_deepseek_key()

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

c = TestClient(main.app)
print("stats before:", c.get("/stats").json()["totals"])

r = c.post("/rag", json={"question": "todos 表有哪些字段？", "k": 3})
print("POST /rag ->", r.status_code)
assert r.status_code == 200, r.text

s = c.get("/stats").json()
print("window:", s["window_days"], "| totals:", s["totals"])
for g in s["groups"]:
    print(f"  {g['kind']:<5} {g['name']:<12} count={g['count']} err={g['errors']} "
          f"avg={g['avg_latency_ms']}ms p95={g['p95_latency_ms']}ms "
          f"tok={g['tokens_in']}/{g['tokens_out']} cost=${g['cost_usd']}")

assert s["totals"]["count"] >= 1
assert any(g["kind"] == "rag" for g in s["groups"])
assert s["totals"]["tokens_in"] > 0
print("\nOBS OK")