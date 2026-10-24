r"""从 ~/.codex/config.toml 读取 todo_rag 的配置并真的拉起它 —— 验证"注册进 Codex"这一步是通的。

只调只读工具（list_todos / search_docs），不会改动真实待办。

用法：
    .\.venv\Scripts\python.exe tests\mcp_from_config.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

import tomllib  # noqa: E402

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

CONFIG = Path(os.path.expanduser("~")) / ".codex" / "config.toml"


def load_server() -> dict:
    data = tomllib.load(open(CONFIG, "rb"))
    servers = data.get("mcp_servers", {})
    assert "todo_rag" in servers, f"config 里没有 todo_rag，现有：{sorted(servers)}"
    return servers["todo_rag"]


def value(result):
    sc = getattr(result, "structured_content", None)
    if isinstance(sc, dict) and "result" in sc:
        return sc["result"]
    return json.loads(result.content[0].text)


async def main():
    cfg = load_server()
    print("config:", {k: cfg[k] for k in cfg if k in ("command", "args", "enabled")})
    assert cfg.get("enabled", True), "todo_rag 被禁用了"
    assert Path(cfg["command"]).is_file(), cfg["command"]
    assert Path(cfg["args"][0]).is_file(), cfg["args"][0]

    params = StdioServerParameters(
        command=cfg["command"],
        args=list(cfg["args"]),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        cwd=str(APP),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = sorted(t.name for t in (await session.list_tools()).tools)
            print("tools:", tools)
            todos = value(await session.call_tool("list_todos", {}))
            print("real todos:", [t["name"] for t in todos])
            hits = value(await session.call_tool("search_docs", {"query": "Swagger 白屏", "k": 2}))
            print("search:", [(h["source"], h["start_line"]) for h in hits])
    print("\nconfig-driven MCP OK")


if __name__ == "__main__":
    asyncio.run(main())