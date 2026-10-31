r"""可观测冒烟：/rag 与 /agent-raw 打点 → /stats 汇总；/stats-ui 可访问。

/rag 会真实调用一次模型（约 1k token）；/agent-raw 用假客户端，不花钱。
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


class _Usage:
    def __init__(self, i, o):
        self.prompt_tokens = i
        self.completion_tokens = o


class _Msg:
    def __init__(self, c):
        self.content = c


class _Choice:
    def __init__(self, c):
        self.message = _Msg(c)


class _Resp:
    def __init__(self, c):
        self.choices = [_Choice(c)]
        self.usage = _Usage(100, 20)


class _Completions:
    def __init__(self, texts):
        self.texts = texts

    async def create(self, **kwargs):
        return _Resp(self.texts.pop(0) if self.texts else "Final Answer: ok")


class _Chat:
    def __init__(self, texts):
        self.completions = _Completions(texts)


class FakeClient:
    def __init__(self, texts):
        self.chat = _Chat(texts)


c = TestClient(main.app)
print("stats before:", c.get("/stats").json()["totals"])
print("/stats-ui ->", c.get("/stats-ui").status_code)

# 1) 真实 /rag
r = c.post("/rag", json={"question": "todos 表有哪些字段？", "k": 3})
print("POST /rag ->", r.status_code)
assert r.status_code == 200, r.text

# 2) 假客户端跑 /agent-raw（验证 ReAct 的 token 累计与打点）
main.get_client = lambda: FakeClient(["Thought: 不用工具\nFinal Answer: ok"])
r = c.post("/agent-raw", json={"messages": [{"role": "user", "content": "测试"}]})
print("POST /agent-raw ->", r.status_code)
assert r.status_code == 200, r.text

s = c.get("/stats").json()
print("window:", s["window_days"], "| totals:", s["totals"])
for g in s["groups"]:
    print(f"  {g['kind']:<5} {g['name']:<16} n={g['count']} err={g['errors']} "
          f"avg={g['avg_latency_ms']}ms tok={g['tokens_in']}/{g['tokens_out']} cost=${g['cost_usd']}")

kinds = {(g["kind"], g["name"]) for g in s["groups"]}
assert ("rag", "POST /rag") in kinds
assert ("agent", "POST /agent-raw") in kinds
agent = next(g for g in s["groups"] if g["name"] == "POST /agent-raw")
assert agent["tokens_in"] == 100 and agent["tokens_out"] == 20, agent
assert s["totals"]["tokens_in"] > 0
assert "proposals" in s
assert s["proposals"]["total"] == 0

print("\nOBS OK")
