r"""待办接口冒烟测试：CRUD、持久化、业务校验、agent 读库。

用临时 DB（TODO_DB 环境变量）隔离，不碰真实的 todos.db。

用法（在项目目录下）：
    .\.venv\Scripts\python.exe tests\smoke_test.py
"""

import importlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

# 先指好临时库，再 import main（否则 main 读到的就是真实路径）
TMP_DIR = Path(tempfile.mkdtemp(prefix="todo-db-"))
os.environ["TODO_DB"] = str(TMP_DIR / "test.db")

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def fresh_client():
    """模拟「重启服务」：重新执行 main 模块（内存清空，DB 文件保留）。"""
    importlib.reload(main)
    return TestClient(main.app)


# ---------------- 假模型（给 T5 用，不用改） ----------------

class _Msg:
    def __init__(self, c): self.content = c
class _Choice:
    def __init__(self, c): self.message = _Msg(c)
class _Resp:
    def __init__(self, c): self.choices = [_Choice(c)]
class _Completions:
    def __init__(self, o): self.o = o
    async def create(self, **kw):
        self.o.calls.append(kw)
        return _Resp(self.o.texts.pop(0) if self.o.texts else "")
class _Chat:
    def __init__(self, o): self.completions = _Completions(o)
class FakeClient:
    def __init__(self, texts):
        self.texts = list(texts); self.calls = []; self.chat = _Chat(self)


# ---------------- 五个测试（断言 TODO 自己填） ----------------
    # TODO 1: 状态码是 200
    # TODO 2: len(body) == 3
    # TODO 3: 每条恰好有 id / name / completed 三个键（提示：set(body[0].keys()) == {...}）
    # TODO 4: completed 是 bool（提示：all(isinstance(t["completed"], bool) for t in body)）
def t1_get_seeds():
    """T1 读：返回 3 条种子，类型不能变味。"""
    c = fresh_client()
    r = c.get("/api/todos")
    body = r.json()

    assert r.status_code == 200
    assert len(body) == 3
    assert set(body[0].keys()) == {"id", "name", "completed"}
    assert all(isinstance(t["completed"], bool) for t in body)

    return f"status={r.status_code} n={len(body)}"


def t2_persist():
    """T2 写 + 持久化：这条过了，才叫真落库。"""
    c = fresh_client()
    r = c.post("/api/todos", json={"name": "验证持久化"})
    assert r.status_code == 201
    assert "id" in r.json()

    c2 = fresh_client()
    names = [t["name"] for t in c2.get("/api/todos").json()]

    assert "验证持久化" in names
    return f"names_after_restart={names}"




def t3_delete():
    """T3 删：200 / 404 两个分支都要在。"""
    c = fresh_client()
    todos = c.get("/api/todos").json()
    target = todos[0]["id"]

    r = c.delete(f"/api/todos/{target}")
    assert r.status_code == 200

    remaining_todos = c.get("/api/todos").json()
    assert len(remaining_todos) == len(todos) - 1

    r_nonexistent = c.delete("/api/todos/99999")
    assert r_nonexistent.status_code == 404

    return f"before={len(todos)}"



def t4_blank_name():
    """T4（加分）业务校验没被改造弄丢。"""
    c = fresh_client()
    r = c.post("/api/todos", json={"name": "   "})

    assert r.status_code == 400
    assert r.json()["detail"] == "name 不能为空"

    return f"status={r.status_code}"



def t5_agent_reads_db():
    """T5（加分）agent 的 query_todos 读的是库，不是启动时的快照。"""
    c = fresh_client()
    c.post("/api/todos", json={"name": "只有库里才有的待办"})

    fake = FakeClient([
        "Thought: 查一下\nAction: query_todos\nAction Input: {}",
        "Thought: 好了\nFinal Answer: 查到了",
    ])
    main.get_client = lambda: fake          # 不联网：把真 client 换成假的
    r = c.post("/agent-raw", json={"messages": [{"role": "user", "content": "列一下待办"}]})

    assert r.status_code == 200
    assert len(fake.calls) >= 2
    assert "只有库里才有的待办" in str(fake.calls[1]["messages"])

    return f"status={r.status_code} calls={len(fake.calls)}"



# ---------------- 跑 ----------------

def run(name, fn):
    try:
        return name, True, fn() or ""
    except NotImplementedError as e:
        return name, False, f"未实现：{e}"
    except AssertionError as e:
        return name, False, f"断言失败：{e}"
    except Exception as e:  # noqa: BLE001
        return name, False, f"{type(e).__name__}: {e}"


def main_run():
    results = [
        run("T1 读种子", t1_get_seeds),
        run("T2 写+持久化", t2_persist),
        run("T3 删除", t3_delete),
        run("T4 空 name（加分）", t4_blank_name),
        run("T5 agent 读库（加分）", t5_agent_reads_db),
    ]
    print()
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<22} {detail}")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} 通过")
    print(f"临时库：{os.environ['TODO_DB']}（跑完自动删除）")
    shutil.rmtree(TMP_DIR, ignore_errors=True)
    if passed < len(results):
        sys.exit(1)


if __name__ == "__main__":
    main_run()