# 可观测（最小闭环，2026-10-24）

> 目标：回答三个问题 —— **这周花了多少、哪类请求最慢、失败率多少**。
> 原则：只记事后有用的字段；**不记 key、不记完整答案**；日志写失败不能拖垮主流程。

## 1. 事件模型

一行一个事件，落到 `logs/events-YYYYMMDD.jsonl`（每天一个文件，已 gitignore）：

```json
{"ts":"2026-10-24T10:30:12","kind":"rag","name":"POST /rag","ok":true,
 "latency_ms":1002,"tokens_in":907,"tokens_out":83,"cost_usd":0.000336,
 "error":null,"meta":{"k":3,"sources":3,"question_len":12}}
```

| 字段 | 含义 |
|---|---|
| `kind` | `rag` / `chat` / `agent` / `tool`（后续可加 `eval`） |
| `name` | `POST /rag`、`mcp.search_docs` … |
| `ok` / `error` | 成功与否、异常类型名（不含堆栈） |
| `latency_ms` | 端到端耗时 |
| `tokens_in/out` | 模型用量 |
| `cost_usd` | 按单价估算（见下） |
| `meta` | 少量结构化上下文（k、命中块数、问题长度、工具参数摘要） |

**不记**：问题原文/答案原文（只记长度）、key、完整工具参数（只记摘要）。

## 2. 打点位置

| 位置 | 事件 | 说明 |
|---|---|---|
| `POST /rag` | `rag / POST /rag` | 成功与失败都记；失败带异常类型 |
| `POST /agent` | `agent / POST /agent` | 两次模型调用的 token 累加；含 `used_tool` |
| `POST /agent-raw` | `agent / POST /agent-raw` | ReAct 每轮 token 累加；含 `steps` / `used_tool` |
| `POST /chat` | `chat / POST /chat` | 流式接口：记耗时与消息数（流式未取 usage，token 记 0） |
| MCP 5 个工具 | `tool / mcp.<name>` | 装饰器 `@traced(...)`，成功/失败/耗时 |

## 3. 汇总接口

`GET /stats?days=7`（days 限制 1–90）返回 JSON；可视化页面：`GET /stats-ui`（单文件，无外部依赖）。

JSON 示例：

```json
{
  "window_days": 7,
  "rates_usd_per_m": {"in": 0.27, "out": 1.10},
  "totals": {"count": 6, "errors": 0, "tokens_in": 907, "tokens_out": 83,
             "cost_usd": 0.000336, "avg_latency_ms": 1002,
             "p95_latency_ms": 1002, "error_rate": 0.0},
  "groups": [{"kind": "rag", "name": "POST /rag", ...}]
}
```

## 4. 成本口径

`obs.py` 里的默认单价（美元 / 每百万 token）按 DeepSeek 公开价设置，可用环境变量覆盖：

```
DEEPSEEK_PRICE_IN=0.27
DEEPSEEK_PRICE_OUT=1.10
```

> 单价变了就改环境变量，不用改代码；日志里已经写死当次估算值，历史不会漂。

## 5. 已验证

```powershell
.\.venv\Scripts\python.exe tests\obs_smoke.py     # /rag → /stats（临时 OBS_DIR）
$env:OBS_DIR="$env:TEMP\obs-mcp"; .\.venv\Scripts\python.exe tests\mcp_smoke.py
```

实测（2026-10-24，`tests/obs_smoke.py`）：
- `/rag` 一次：`907/69 token, $0.000321, 1064ms`；
- `/agent-raw` 用假客户端：token 累计 `100/20`，事件落盘正确；
- `/stats-ui` 返回 200；
- MCP 冒烟产生 5 条 `tool` 事件（list/add/list/delete/search），`search_docs` 因进程内首次加载 embedding 模型耗时约 1.7s。

## 6. 限制与下一步

- 没有告警：失败率/成本突增目前靠人看；
- 没有轮转清理：按天一个文件，定期手动清 `logs/`；
- `/chat` 是流式接口，未开启 `stream_options.include_usage`，因此 token 记 0（只有耗时）；
- 面板是手刷新的，没有自动轮询曲线。