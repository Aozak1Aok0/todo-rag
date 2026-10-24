# MCP Server 设计（todo-rag）

> 2026-10-24 · 把项目里的「待办」和「本地 RAG」暴露成 MCP 工具，让 Codex / Claude 直接调用。
> 代码：`mcp_server.py`（`mcp` 2.x 的 `MCPServer`）· 测试：`tests/mcp_smoke.py`

## 1. 目标 / 非目标

**目标**
- 客户端（Codex / Claude Desktop）能：读待办、加/删待办、检索本地语料、基于语料问答。
- 与 Web 端共用同一份实现（`store.py` / `rag/rag.py` / `rag/prompt.py`），不允许出现两套 SQL 或两套提示词。
- key 不落盘：优先环境变量，其次 Windows 凭据管理器（目标名可用 `CRED_TARGET` 覆盖）。

**非目标（本期不做）**
- HTTP / SSE transport、鉴权、多用户隔离；
- 写操作的人工确认流程（交给客户端审批）；
- 流式返回（`ask_docs` 一次性返回）。

## 2. 架构

```
Codex / Claude ──stdio(JSON-RPC)──▶ mcp_server.py (MCPServer)
                                     ├─ list_todos / add_todo / delete_todo  ──▶ store.py ──▶ todos.db
                                     ├─ search_docs                        ──▶ rag.rag.retrieve
                                     └─ ask_docs                           ──▶ rag.prompt + DeepSeek
```

## 3. 工具清单

| 工具 | 读/写 | 说明 | 返回 |
|---|---|---|---|
| `list_todos` | 读 | 全部待办 | `[{id, name, completed}]` |
| `add_todo(name)` | **写** | trim 后为空报错 | `{id, name, completed:false}` |
| `delete_todo(todo_id)` | **写** | 不存在返回 `deleted:false` | `{deleted, id}` |
| `search_docs(query, k=5)` | 读 | 混合检索（k 限制 1–10） | `[{source, start_line, end_line, distance, preview}]` |
| `ask_docs(question, k=8)` | 读（花钱） | 检索 + DeepSeek 回答 | `{answer, sources, usage}` |

资源（只读快照）：

| URI | 内容 |
|---|---|
| `todos://all` | 待办 JSON |
| `docs://index` | 索引的块数与来源分布 |

## 4. 关键决策

1. **stdio 而不是 HTTP**：本地单用户工具，客户端负责拉起进程；没有端口/鉴权负担。以后要给别的机器用再上 streamable-http。
2. **写工具直说**：`description` 里标明"写入操作"，让客户端的审批 UI 能提示。MCP 本身不替你确认。
3. **复用而不是复制**：`store.py` 是 Web 与 MCP 的唯一数据层；`rag/prompt.py` 是唯一提示词来源（当前默认变体 C）。
4. **key 不进配置**：`credentials.py` 用 ctypes 调 `CredReadW` 读通用凭据，Codex 配置里不需要 `env`。

## 5. 注册到 Codex

`~/.codex/config.toml` 末尾（已写入）：

```toml
[mcp_servers.todo_rag]
command = '<repo>\.venv\Scripts\python.exe'
args = ['<repo>\mcp_server.py']
enabled = true
```

重启 Codex 后，新会话即可看到 `todo_rag` 的工具。
Claude Desktop 则是在 `claude_desktop_config.json` 的 `mcpServers` 里写同一组 `command` / `args`。

## 6. 验证（本地、可重复）

```powershell
cd <repo>
.\.venv\Scripts\python.exe tests\mcp_smoke.py             # 工具/资源/读写，约 5 秒
.\.venv\Scripts\python.exe tests\mcp_smoke.py --with-llm  # 额外一次 ask_docs（会花钱）
```

`tests/mcp_smoke.py` 会真的拉起 stdio 子进程，断言：5 个工具存在、种子 3 条、加/删生效、`search_docs` 命中 `main.py`、两个资源可列出；`--with-llm` 还验证凭据读取与一次真实问答（in≈1.5k token）。

## 7. 已知限制

- 没有审计日志：谁在什么时候调了写工具，目前查不到（见 `observability.md`）。
- `ask_docs` 非流式；检索是同步的，服务端已用 `anyio.to_thread` 包了一层。
- 工具返回里的 `preview` 是纯文本截断，没有做 markdown 清洗。
- 客户端若自动批准写工具，存在误删风险 —— 建议在客户端里对 `add_todo` / `delete_todo` 保持"每次确认"。

## 8. 下一步

1. 给工具调用加 trace（时间、耗时、参数摘要、token），落到 `logs/mcp.jsonl`；
2. 加 `update_todo(id, completed)`，补齐 CRUD；
3. 需要跨设备时，切 streamable-http + token 鉴权。