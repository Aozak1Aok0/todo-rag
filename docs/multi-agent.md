# 多 Agent：Supervisor + Todo / Docs specialist（2026-10-27）

> 代码：`agents/orchestrator.py` · 接口：`POST /multi-agent` · 测试：`tests/multi_agent_smoke.py`
> 路由评测：`evals/routing_eval.py` · 结果：`evals/routing-20261027.jsonl`

## 1. 它和 `/rag-verify` 有什么区别

- `/rag-verify` 是**纵向**双 Agent：回答 Agent 生成草稿，校验 Agent 独立核查；解决的是「答案有没有资料依据」。
- `/multi-agent` 是**横向**多 Agent：Supervisor 判断问题该交给谁，Todo Agent 和 Docs Agent 各自处理，必要时再汇总。

```
                      ┌─ Todo Agent（确定性读 SQLite）
问题 → Supervisor ────┤
                      └─ Docs Agent（检索 + 回答 + 校验）
                                  │
                          route=both 时 → Synthesizer 汇总
```

这里没有让每个 Agent 自由对话到收敛。一次请求最多：

1. 1 次 Supervisor 路由；
2. 1 次 Todo 读取，或 1 次 Docs 流水线，或两者都跑；
3. route=both 时 1 次汇总。

这样延迟和 token 可解释，也不会出现 Agent 互相调用停不下来。

## 2. 分工与安全边界

| 角色 | 做什么 | 不做什么 |
|---|---|---|
| Supervisor | 输出 `todos / docs / both` 与两个子问题 | 不回答业务问题 |
| Todo Agent | 确定性读取 SQLite，按「全部 / 未完成 / 已完成」过滤 | 不新增、不删除、不修改；写请求直接说明只读并给 API 路径 |
| Docs Agent | 复用 `rag.pipeline.answer_verified`（多查询 + 回答 + 校验） | 不读待办，不碰数据库 |
| Synthesizer | 只合并两个 specialist 的输出 | 不补充新事实，不改待办名称 / id / 状态 |

Todo 走确定性代码而不是 LLM，是有意的：待办名称、id、完成状态是结构化事实，让模型复述只会多一个幻觉面。

## 3. 接口

```http
POST /multi-agent
Content-Type: application/json

{"question": "我有多少条待办、多少条未完成？并说明 /rag-verify 是怎么做校验的", "k": 10}
```

返回关键字段：

```json
{
  "answer": "……",
  "route": "both",
  "plan": {"route": "both", "reason": "……", "todos_query": "……", "docs_query": "……"},
  "trace": [
    {"agent": "supervisor", "status": "ok", "latency_ms": 1517, "in": 204, "out": 84},
    {"agent": "todos", "status": "ok", "latency_ms": 3, "detail": "2/3 条"},
    {"agent": "docs", "status": "ok", "latency_ms": 6020, "in": 7968, "out": 562},
    {"agent": "synthesizer", "status": "ok", "latency_ms": 1974, "in": 628, "out": 496}
  ],
  "sources": [{"source": "python/fastapi-api/main.py", "start_line": 419, "end_line": 448}],
  "verification": {"verdict": "ok", "unsupported": []},
  "usage": {"in": 8800, "out": 1142}
}
```

`sources` 只来自 Docs Agent；`verification` 也只覆盖文档部分，不校验待办事实。route=both 时 UI 会标成「文档部分校验」。

## 4. 路由评测

10 条人工标注问题，覆盖单待办、单文档、混合问题和一个写操作（预期仍然路由到 todos，由 Todo Agent 拒绝写入）：

```powershell
.\.venv\Scripts\python.exe evals\routing_eval.py
```

实测（2026-10-27，DeepSeek `deepseek-chat`）：

- **路由正确 10/10**；
- Supervisor 单次约 **0.9–1.2 s**；
- 10 次路由合计约 10 s。

路由评测只测「分派对不对」，不测最终答案质量；答案质量仍由 RAG 的 10 题评测与人工复核负责。

## 5. 实测样例

问题：`我有多少条待办、多少条未完成？并说明 /rag-verify 是怎么做校验的`

- route：`both`
- 四个 Agent 全部 `ok`
- 总用量：`8800 in / 1142 out`
- 端到端约 9.5 s
- 待办部分由 SQLite 直接生成，只返回计数（问题含「多少条」时不展开待办名称）；文档部分带 10 条引用；汇总没有新增待办事实

这只是单次采样，不能当成稳定延迟承诺。固定成本主要来自 Docs Agent 的多查询和校验。

## 6. 验证

```powershell
.\.venv\Scripts\python.exe tests\multi_agent_smoke.py
```

离线测试不联网、不花 token，覆盖：

- 路由 JSON 解析与坏 JSON 回退 docs；
- Todo Agent 的全部 / 未完成 / 已完成过滤；
- 写请求被只读策略拦截；
- todos / docs / both 三条路径与 trace；
- `POST /multi-agent` HTTP 端点。

前端：`web/` 里切到「多 Agent」模式，或点示例 chip；答案下方会显示路由与每条 Agent 轨迹。

## 7. 已知限制与下一步

- Todo Agent 目前只读；写操作需要「模型提议 → 人工确认 → 执行」的审批链，不能直接放开。
- route=both 目前是顺序执行（Todo 很快，Docs 是瓶颈）；可以把 Todo 与 Docs 放进 `asyncio.gather`，但收益很小。
- Supervisor 只有三个路由，问题超出代码库/待办范围时会落到 docs，由 RAG 回答「资料中没有」。
- 下一步可以做：写操作确认链、按文件/模块拆多个 Docs specialist、把 trace 落到可观测日志并在 `/stats` 单独聚合。
