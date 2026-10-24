r"""MCP server：把「待办」和「本地 RAG」暴露给 Codex / Claude（stdio transport）。

设计取舍：
- **stdio**：本地单用户工具，stdio 最简单，不需要鉴权/端口；客户端负责拉起进程。
- **读写分离**：list_todos / search_docs 只读；add_todo / delete_todo 会改库，描述里明确写出来。
- **key 不落盘**：ask_docs 用 credentials.get_deepseek_key()（环境变量 → Windows 凭据管理器）。
- **复用同一份实现**：待办走 store.py，检索走 rag/rag.py，提示词走 rag/prompt.py，
  和 Web 端不是两套代码。

启动（客户端一般会自己拉起，不需要手动跑）：
    .\.venv\Scripts\python.exe mcp_server.py
"""

import functools
import inspect
import json
import sys
import time
from collections import Counter
from pathlib import Path

APP = Path(__file__).resolve().parent
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import anyio  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402

import obs  # noqa: E402
import store  # noqa: E402
from credentials import get_deepseek_key  # noqa: E402

store.init_db()  # MCP 服务启动时也保证表存在（与 Web 端共用同一份建表逻辑）

BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-chat"

server = MCPServer(
    name="todo-rag",
    version="0.1.0",
    instructions=(
        "这是本机 todo-rag 项目的工具服务：可以读写 SQLite 待办，也可以在项目的 15 个文件语料上做检索问答。"
        "search_docs 只返回片段（带文件名与行号）；ask_docs 会调用 DeepSeek 生成回答并返回引用。"
    ),
)




def _brief(args, kwargs) -> str:
    parts = []
    if args:
        parts.append(f"args={args!r}")
    if kwargs:
        parts.append(f"kwargs={kwargs!r}")
    return "; ".join(parts)[:240]


def traced(name: str):
    """给 MCP 工具加 trace：成功/失败、耗时、参数摘要（不记返回值）。"""
    def deco(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def aw(*a, **kw):
                t0 = time.time()
                try:
                    out = await fn(*a, **kw)
                    obs.log_event("tool", name, ok=True, latency_ms=int((time.time() - t0) * 1000),
                                  args=_brief(a, kw))
                    return out
                except Exception as e:  # noqa: BLE001
                    obs.log_event("tool", name, ok=False, error=type(e).__name__,
                                  latency_ms=int((time.time() - t0) * 1000), args=_brief(a, kw))
                    raise
            return aw

        @functools.wraps(fn)
        def w(*a, **kw):
            t0 = time.time()
            try:
                out = fn(*a, **kw)
                obs.log_event("tool", name, ok=True, latency_ms=int((time.time() - t0) * 1000),
                              args=_brief(a, kw))
                return out
            except Exception as e:  # noqa: BLE001
                obs.log_event("tool", name, ok=False, error=type(e).__name__,
                              latency_ms=int((time.time() - t0) * 1000), args=_brief(a, kw))
                raise
        return w
    return deco

# ---------------- 待办（读/写） ----------------

@server.tool(description="列出所有待办事项（只读）")
@traced("mcp.list_todos")
def list_todos() -> list[dict]:
    return store.list_todos()


@server.tool(description="新增一条待办；name 会 trim，空字符串会报错（写入操作）")
@traced("mcp.add_todo")
def add_todo(name: str) -> dict:
    return store.add_todo(name)


@server.tool(description="按 id 删除一条待办，返回 {deleted: bool, id}（写入操作）")
@traced("mcp.delete_todo")
def delete_todo(todo_id: int) -> dict:
    return {"deleted": store.remove_todo(todo_id), "id": todo_id}


# ---------------- RAG（检索 / 问答） ----------------

def _compact(h: dict) -> dict:
    body = h["text"].split("\n", 1)[-1]
    return {
        "source": h["source"],
        "start_line": h["start_line"],
        "end_line": h["end_line"],
        "distance": round(h["distance"], 4) if h["distance"] is not None else None,
        "preview": body[:240],
    }


@server.tool(description="在本地项目语料里做混合检索（向量 + BM25），返回 top-k 片段及来源行号")
@traced("mcp.search_docs")
def search_docs(query: str, k: int = 5) -> list[dict]:
    from rag.rag import retrieve

    k = max(1, min(int(k), 10))
    return [_compact(h) for h in retrieve(query, k)]


@server.tool(description="先检索本地语料、再让 DeepSeek 回答；返回 answer / sources / usage")
@traced("mcp.ask_docs")
async def ask_docs(question: str, k: int = 8) -> dict:
    from rag.prompt import build_rag_messages
    from rag.rag import retrieve

    question = (question or "").strip()
    if not question:
        raise ValueError("question 不能为空")
    k = max(1, min(int(k), 10))

    hits = await anyio.to_thread.run_sync(retrieve, question, k)
    messages = build_rag_messages(question, hits)

    client = AsyncOpenAI(api_key=get_deepseek_key(), base_url=BASE_URL)
    resp = await client.chat.completions.create(
        model=MODEL, messages=messages, temperature=0
    )
    usage = resp.usage
    return {
        "answer": resp.choices[0].message.content or "",
        "sources": [_compact(h) for h in hits],
        "usage": {
            "in": usage.prompt_tokens if usage else 0,
            "out": usage.completion_tokens if usage else 0,
        },
    }


# ---------------- 资源（只读快照） ----------------

@server.resource("todos://all", mime_type="application/json", description="全部待办的 JSON 快照")
def todos_resource() -> str:
    return json.dumps(store.list_todos(), ensure_ascii=False, indent=2)


@server.resource("docs://index", mime_type="text/plain", description="检索索引的块数与来源分布")
def docs_index() -> str:
    from rag.rag import get_client, get_collection

    col = get_collection(get_client(), create=False)
    d = col.get(include=["metadatas"])
    counts = Counter(m["source"] for m in d["metadatas"])
    lines = [f"{v:3d}  {k}" for k, v in sorted(counts.items())]
    return "\n".join(lines) + f"\n\n共 {sum(counts.values())} 块"


if __name__ == "__main__":
    server.run("stdio")