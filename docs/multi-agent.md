# 多 Agent：Supervisor + Todo / Docs specialist（2026-10-27）

> 代码：`agents/orchestrator.py`、`agents/write_planner.py`、`agents/approvals.py`、`agents/todo_writes.py`
> 接口：`POST /multi-agent`、`POST /multi-agent/approve`
> 测试：`tests/multi_agent_smoke.py` · 路由评测：`evals/routing_eval.py`

## 1. 它和 `/rag-verify` 有什么区别

- `/rag-verify` 是**纵向**双 Agent：回答 Agent 生成草稿，校验 Agent 独立核查；解决的是「答案有没有资料依据」。
- `/multi-agent` 是**横向**多 Agent：Supervisor 判断问题该交给谁，Todo Agent 和 Docs Agent 各自处理，必要时再汇总。

```
                      ┌─ Todo Agent（读：确定性 SQLite）
问题 → Supervisor ────┤
                      │   └─ 写：Write Planner → proposal → 人工确认 → 执行
                      └─ Docs Agent（检索 + 回答 + 校验）
                                  │
                          route=both 时 → Synthesizer 汇总
```

这里没有让每个 Agent 自由对话到收敛。一次请求最多：

1. 1 次 Supervisor 路由；
2. 1 次 Todo 读取 / Write Planner，或 1 次 Docs 流水线，或两者都跑；
3. route=both 且没有待确认写操作时，1 次汇总。

这样延迟和 token 可解释，也不会出现 Agent 互相调用停不下来。

## 2. 分工与安全边界

| 角色 | 做什么 | 不做什么 |
|---|---|---|
| Supervisor | 输出 `todos / docs / both`、`intent=read/write` 与两个子问题 | 不回答业务问题，不执行写操作 |
| Todo Agent（读） | 确定性读取 SQLite，按「全部 / 未完成 / 已完成」过滤 | 不新增、不删除、不修改 |
| Write Planner | 把写请求转成单个结构化 proposal | 不执行 SQL，不声称已经完成 |
| Docs Agent | 复用 `rag.pipeline.answer_verified`（多查询 + 回答 + 校验） | 不读待办，不碰数据库 |
| Synthesizer | 只合并两个 specialist 的读取结果 | 不补充新事实，不改待办名称 / id / 状态 |

Todo 读取走确定性代码而不是 LLM，是有意的：待办名称、id、完成状态是结构化事实，让模型复述只会多一个幻觉面。
写操作则相反：模型负责把自然语言变成结构化动作，**执行权留在人工确认之后**。

## 3. 写操作审批链

### 3.1 两阶段

```
用户：把「学 Rust」加到待办
  │
  ├─ Supervisor：route=todos, intent=write
  ├─ Write Planner：{"action":"add_todo","args":{"name":"学 Rust"}}
  ├─ 服务端校验 + 创建 proposal（随机 id、5 分钟、单次使用）
  └─ 返回给前端：proposal（pending）
          │
          └─ 用户点「确认执行」
                └─ POST /multi-agent/approve
                      └─ 执行 SQLite 写入 → 返回执行结果
```

关键点：

- 模型**不能**直接写库；`Write Planner` 的输出只是数据；
- 服务端会再次校验 action、参数、todo id 是否存在；
- proposal 有过期时间，消费一次后失效；
- 用户点「取消」只作废 proposal，不碰数据库；
- 执行时如果目标待办已经被别处删除，返回 `409`，不会写入脏数据。

### 3.2 proposal 生命周期

| 状态 / 结果 | 含义 |
|---|---|
| `pending` | 已生成，等待人工确认；默认 5 分钟有效 |
| `executing` | 已被某个进程抢占，正在执行 |
| `executed` | 已确认并成功写入 |
| `cancelled` | 用户取消，未修改数据 |
| `failed` | 执行失败，不会重试 |
| `expired` | 超过有效期，已作废 |
| `404` | proposal 不存在、已消费或已取消 |
| `410` | proposal 已过期 |
| `409` | 执行时目标数据已变化（如待办被删） |

proposal 落在 `TODO_DB` 的 `agent_proposals` 表，服务重启不会丢；`claim` 用 SQLite 条件更新做单次抢占，因此单进程多 worker 也不会重复执行。
`executing` 超过 `PROPOSAL_STALE_SECONDS`（默认 60 秒）会在下一次 claim / 审计查询时标记为 `failed`，结果里带 `{"error":"stale_executing"}`。
多用户部署仍需要登录态 / 权限绑定；当前 proposal id 本身就是 bearer token。

## 4. 接口

### 4.1 发起请求

```http
POST /multi-agent
Content-Type: application/json

{"question": "把「学 Rust」加到待办", "k": 10}
```

写请求返回 `status=approval_required` 和 `proposal`：

```json
{
  "answer": "我准备新增待办：「学 Rust」。这是写操作，确认后才会执行。",
  "status": "approval_required",
  "route": "todos",
  "plan": {"route": "todos", "intent": "write", "reason": "……"},
  "proposal": {
    "id": "riE9wbns2PfgUP00LFW1nvY9",
    "action": "add_todo",
    "args": {"name": "学 Rust"},
    "summary": "新增待办：「学 Rust」",
    "status": "pending",
    "expires_at": "2026-10-27T22:28:29",
    "expires_in_seconds": 299
  },
  "trace": [
    {"agent": "supervisor", "status": "ok", "detail": "todos"},
    {"agent": "todo_planner", "status": "ok", "detail": "add_todo"}
  ]
}
```

读取问题仍然直接返回答案，不会有 proposal：

```json
{
  "answer": "当前共有 3 条待办……",
  "status": "ok",
  "route": "todos",
  "proposal": null
}
```

### 4.2 确认或取消

```http
POST /multi-agent/approve
Content-Type: application/json

{"proposal_id": "riE9wbns2PfgUP00LFW1nvY9", "approved": true}
```

确认成功后：

```json
{
  "status": "executed",
  "proposal_id": "riE9wbns2PfgUP00LFW1nvY9",
  "action": "add_todo",
  "result": {"message": "已新增待办 #4：「学 Rust」", "todo": {"id": 4, "name": "学 Rust", "completed": false}},
  "todos": []
}
```

`approved=false` 返回 `status=cancelled`，数据库不变。

支持的动作：

| action | args | 说明 |
|---|---|---|
| `add_todo` | `{"name": "..."}` | 新增 |
| `delete_todo` | `{"todo_id": 3}` | 删除 |
| `set_completed` | `{"todo_id": 3, "completed": true}` | 标记完成 / 未完成 |

### 4.3 审计查询

```http
GET /multi-agent/proposals?status=executed&limit=20
GET /multi-agent/proposals/{proposal_id}
```

返回 proposal 的 action、args、summary、status、`created_at`、`claimed_at`、`finished_at` 和 `result`。
`status` 可选：`pending / executing / executed / cancelled / failed / expired`。

前端页面下方有「最近写操作」面板，显示最近 6 条 proposal 的状态与结果。
和 todo API 一样，审计接口默认没有鉴权，只适合本地单用户；公网部署前必须加登录态。

`GET /stats?days=7` 也会返回 `proposals` 聚合：状态分布、按动作拆分、确认/取消/失败率、stale 回收数、决策耗时与 p95。

## 5. 文档部分与 `/rag-verify`

Docs Agent 复用 `pipeline.answer_verified`，所以返回里的 `sources` 和 `verification` 只覆盖文档部分；
待办事实不参与文档校验。route=both 时 UI 会标成「文档部分校验」。

## 6. 路由评测

10 条人工标注问题，覆盖单待办、单文档、混合问题和一个写操作（写请求正确路由到 todos，再由 Write Planner 生成 proposal）：

```powershell
.\.venv\Scripts\python.exe evals\routing_eval.py
```

实测（2026-10-27，DeepSeek `deepseek-chat`）：

- **路由 + intent 正确 10/10**（其中写请求 R10 必须为 `intent=write`）；
- Supervisor 单次约 **0.6–2.6 s**（含网络波动）；
- 10 次路由合计约 **10–12 s**。

路由评测只测「分派对不对」，不测最终答案质量；答案质量仍由 RAG 的 10 题评测与人工复核负责。

## 7. 实测样例

### 7.1 读取 + 文档

问题：`我有多少条待办、多少条未完成？并说明 /rag-verify 是怎么做校验的`

- route：`both`
- 四个 Agent 全部 `ok`
- 总用量：`8800 in / 1142 out`
- 端到端约 9.5 s
- 待办部分由 SQLite 直接生成，只返回计数（问题含「多少条」时不展开待办名称）；文档部分带 10 条引用

### 7.2 写操作

问题：`把「学 Rust」加到待办`

- route：`todos`，intent：`write`
- proposal：`add_todo`
- 确认前数据库没有「学 Rust」
- 确认后新增成功，proposal 再消费一次返回 `404`
- 真实验证还覆盖了「标记完成」和「删除」两种 action
- 同一个 `TODO_DB` 重启 uvicorn 后，原 proposal 仍能确认执行
- 审计查询能看到 `pending → executed` 的状态和结果；模拟 stale `executing` 后会自动变成 `failed`

这只是单次采样，不能当成稳定延迟承诺。固定成本主要来自 Docs Agent 的多查询和校验。

## 8. 验证

```powershell
.\.venv\Scripts\python.exe tests\multi_agent_smoke.py
```

离线测试不联网、不花 token，覆盖：

- 路由 JSON 解析、坏 JSON 回退、`intent=write` 兜底；
- Todo Agent 的全部 / 未完成 / 已完成过滤；
- Write Planner 生成 proposal，确认前不落库；
- proposal 落 SQLite，重启后仍可 claim；
- 确认执行、取消、单次消费、非法 id、过期、目标已变化（409）、stale 回收、标记完成；
- 审计列表 / 单条查询，以及 `/stats` 中的 proposal 聚合；
- todos / docs / both 三条路径与 trace；
- `POST /multi-agent` 和 `POST /multi-agent/approve` HTTP 端点。

前端：`web/` 里切到「多 Agent」模式，或点示例 chip；写操作会显示「待确认」卡片，只有点「确认执行」才会调用审批接口。

## 9. 已知限制与下一步

- proposal 已落 SQLite，重启不丢；stale `executing` 会标记为 `failed`，但不会自动重试，需要重新发起。
- proposal id 是 bearer token，没有额外鉴权；本地单用户可用，公网部署需要登录态。
- route=both 且有待确认写操作时，不做 LLM 汇总，直接拼接「待办 + 文档」，避免模型改写 proposal 文案。
- route=both 目前顺序执行（Todo 很快，Docs 是瓶颈）；可以把 Todo 与 Docs 放进 `asyncio.gather`，但收益很小。
- 下一步可以做：proposal 用户绑定、把 write planner 的模型调用 trace 写进事件日志、按文件/模块拆多个 Docs specialist。
