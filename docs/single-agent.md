# 单 Agent vs 多 Agent：同一批 8 个用例（2026-11-03）

> 代码：`agents/single.py` · `evals/single_agent_eval.py` · `evals/agent_ab.py`
> 用例：`evals/agent_cases.py`（与 `multi_agent_eval.py` 共用）· 结果：`evals/agent-ab-20261103-2006.md`

## 1. 设计

两套编排，同一批用例、同一个临时 SQLite、同一个回答流水线。

**多 Agent（现状）**：Supervisor 先输出 `route` + `intent` + 子问题，再交给 specialist。待办读取走确定性 SQLite（不经过模型），写操作由 Supervisor 一次调用直接生成 proposal。

**单 Agent**：一个模型 + 3 个工具，最多 4 步工具循环：

| 工具 | 参数 | 做什么 |
|---|---|---|
| `query_todos` | `filter=all/open/done` | 直接查 SQLite，返回确定性文本 |
| `answer_docs` | `question` | 调 `pipeline.answer_verified` |
| `propose_todo_write` | `action` / `name` / `todo_id` / `completed` | 校验后生成 proposal |

没有显式路由：走哪条路由「模型选了什么工具」决定。`route` 事后按用过的工具推断，`both` 仅当两个都用了。

**两边共同点**（保证可比）：写操作一律只生成 proposal，审批仍在 `/multi-agent/approve`；文档回答都调同一个 `answer_verified`；待办文本复用 `orchestrator.answer_todos` 的措辞。

## 2. 方法

- 8 个用例：E1 文档（Swagger）、E2 todos 表结构、E3 待办数、E4 两者、E5 新增、E6 标记完成、E7 删除、E8 删除不存在的 id。
- 检查项与 `multi_agent_eval.py` 完全一致：route、intent、关键词、clarify、action 匹配、审批后 DB 断言。
- 每个用例独立临时 DB 与 obs 目录；温度默认；单次运行。

## 3. 结果

| 用例 | 通过（单/多） | 单 in/out | 多 in/out | 单延迟 | 多延迟 |
|---|---|---|---|---|---|
| E1 文档 | ✓ / ✓ | 8261 / 588 | 6964 / 834 | 7136 ms | 8919 ms |
| E2 表结构 | ✓ / ✓ | 6187 / 450 | 5416 / 392 | 5117 ms | 4713 ms |
| E3 待办数 | ✓ / ✓ | 1545 / 93 | **252 / 45** | 1234 ms | 884 ms |
| E4 两者 | ✓ / ✓ | 8627 / 732 | 7475 / 781 | 7085 ms | 6349 ms |
| E5 新增 | ✓ / ✓ | 720 / 61 | 531 / 106 | 1179 ms | 1821 ms |
| E6 完成 | ✓ / ✓ | 1563 / 113 | **554 / 113** | 1820 ms | 1845 ms |
| E7 删除 | ✓ / ✓ | 1571 / 123 | **556 / 113** | 1499 ms | 2176 ms |
| E8 不存在 id | ✓ / ✓ | 1527 / 100 | **527 / 136** | 1876 ms | 2037 ms |
| **合计** | **8/8 · 8/8** | 30001 / 2260 | 22275 / 2520 | 3368 ms | 3593 ms |

## 4. 发现

1. **准确率打平**：8/8 vs 8/8。至少在这批用例上，Supervisor 那层路由没有带来正确率收益。
2. **成本结构不同，不是「谁更便宜」**：
   - 读待办（E3）：多 Agent 252 token，单 Agent 1545 —— 多 Agent 的确定性路径完全不经过模型。
   - 写操作（E6/E7/E8）：单 Agent 要「先查 id 再写」，两次调用；Supervisor 一次调用就同时给出路由和 proposal payload。
   - 所以单 Agent 在纯读上贵 6 倍，在写上贵 2.5–3 倍，在这批用例里没有找到它更便宜的路径。
3. **延迟**：单平均 3368 ms，多 3593 ms（-6%），但逐题互有胜负，在噪声范围内。
4. **代码量**：单 329 行，多 407 行 Supervisor + 两个 specialist。单 Agent 的优势是可读性与调试简单，不是指标。

## 5. Caveat

三条，缺一条这个结论就站不住：

- **测的是编排，不是回答质量**：文档题两边调同一个 `answer_verified`，回答质量在设计上就不可能不同。
- **单 Agent 的成本有优化空间**：多花的 token 有一半来自「工具返回后再生成一次」。跳过这次复述可以降本，但下限受 tool schema（约 700 token）约束，仍追不平 252。
- **8 题、单次运行**：支持「没发现差异」，不支持「两者等价」。

## 6. 结论

- `/multi-agent` 仍是默认入口：待办读走确定性路径（0 token）、写边界清晰、trace 可观测。
- `agents/single.py` 保留为对照与 fallback，不作为默认。
- 8 个用例量不出差异，下一步是把题库扩到 40 题（30 训练 + 10 holdout）再看是否还打平。

## 7. 复现

```powershell
.\.venv\Scripts\python.exe evals\agent_ab.py
```

输出 `evals/agent-ab-<stamp>.md` 与 `.jsonl`。单独跑某一边：

```powershell
.\.venv\Scripts\python.exe evals\single_agent_eval.py --limit 8
.\.venv\Scripts\python.exe evals\multi_agent_eval.py --limit 8
```
