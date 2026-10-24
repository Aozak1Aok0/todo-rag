r"""MCP server 冒烟测试：真的起一个 stdio 子进程，连上去列工具、调工具。

MCP 2.x 的返回值在 `structured_content["result"]` 里（content 是给人看的文本块）；
这个脚本两种都兼容。

用法（在 fastapi-api 目录下）：
    .\.venv\Scripts\python.exe tests\mcp_smoke.py              # 只读 + 写操作的快速检查
    .\.venv\Scripts\python.exe tests\mcp_smoke.py --with-llm   # 额外调一次 ask_docs（会花钱）
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


def value(result):
    """取工具返回值：优先 structured_content.result，退回解析文本。"""
    sc = getattr(result, "structured_content", None)
    if isinstance(sc, dict) and "result" in sc:
        return sc["result"]
    text = result.content[0].text if result.content else ""
    return json.loads(text)


def text_of(result):
    return result.content[0].text if result.content else ""


async def run(with_llm: bool):
    tmp_db = Path(os.environ.get("TEMP", ".")) / "mcp-smoke.db"
    if tmp_db.exists():
        tmp_db.unlink()
    env = {**os.environ, "TODO_DB": str(tmp_db), "PYTHONIOENCODING": "utf-8"}

    params = StdioServerParameters(
        command=str(APP / ".venv" / "Scripts" / "python.exe"),
        args=[str(APP / "mcp_server.py")],
        env=env,
        cwd=str(APP),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print("tools:", names)
            assert {"list_todos", "add_todo", "delete_todo", "search_docs", "ask_docs"} <= set(names)

            todos = value(await session.call_tool("list_todos", {}))
            print("list_todos:", len(todos), "条 ->", [t["name"] for t in todos])

            added = value(await session.call_tool("add_todo", {"name": "MCP 冒烟"}))
            print("add_todo:", added)
            assert added["name"] == "MCP 冒烟"

            todos = value(await session.call_tool("list_todos", {}))
            assert "MCP 冒烟" in [t["name"] for t in todos], [t["name"] for t in todos]

            deleted = value(await session.call_tool("delete_todo", {"todo_id": added["id"]}))
            print("delete_todo:", deleted)
            assert deleted["deleted"] is True

            hits = value(await session.call_tool("search_docs", {"query": "Swagger 白屏是怎么解决的", "k": 3}))
            print("search_docs:", [(h["source"], h["start_line"]) for h in hits])
            assert any("main.py" in h["source"] for h in hits)

            resources = await session.list_resources()
            print("resources:", [str(x.uri) for x in resources.resources])

            if with_llm:
                data = value(await session.call_tool("ask_docs", {"question": "todos 表有哪些字段？", "k": 5}))
                print("ask_docs:", data["answer"][:120].replace("\n", " "))
                print("usage:", data.get("usage"), "| sources:", len(data.get("sources", [])))

    if tmp_db.exists():
        tmp_db.unlink()
    print("\nMCP smoke OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-llm", action="store_true")
    asyncio.run(run(ap.parse_args().with_llm))