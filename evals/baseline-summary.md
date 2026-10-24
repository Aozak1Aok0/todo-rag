# baseline 摘要 · v1

> ⚠️ **本文件对应 eval v0.1 / commit `218e53a`（内存 list 版）。**
> 2026-10-18 起 `main.py` 已迁移 SQLite，**Q7 与 Q9 的 gold 已失效**，评估集升到 v0.2（见 `rag-eval-10.md` 第 5 节）。
> 这份 baseline 只作**历史对照**：可以拿它说明"当时裸考 1.00 / 开卷 9.42"，但**不能拿来跟新代码比**。新代码请重跑 baseline。
> 数据：`baseline-218e53a-20261016.jsonl`（20 行，10 题 × 2 条件）· 清单：同名 `.manifest.json`
> 代码版本：`218e53a「1015」`（分支 `pa`）· 模型：`deepseek-chat`，`temperature=0`，`max_tokens=1024`
> 语料：`corpus.txt` 里 15 个文件，共 21,834 字符
> 判分：2026-10-17 完成（人工逐题判，口径见下）

## 一句话结论

**不给资料：1.00 / 10，其中 6 道题在编造；把资料全塞进去：9.42 / 10，0 编造。**
→ 「有资料」这件事本身值 **8.42 分**；裸考的主要失败模式不是「不会」，而是「自信地编」。

## 结果

| 条件 | 题均分 | 幻觉题数 | 老实说不会 | 输入 token 合计 | 平均每题输入 |
|---|---|---|---|---|---|
| ① 无上下文（纯模型记忆） | **1.00** / 10 | **6** / 10 | 2 题（Q1、Q5） | 416 | 42 |
| ② 全文塞 prompt（上限） | **9.42** / 10 | 0 / 10 | 0 | 69,306 | 6,931 |

> 平均延迟两条件都约 1.57 s；② 的代价全在输入上（**每题多 6.9k token**），这正是 RAG 要省的那部分。

## 每题明细

| 题 | 题型 | ① noctx | ② fullctx | 备注 |
|---|---|---|---|---|
| Q1 | 路由清单 | 0 / 9 | 9 / 9 | ①诚实拒答，不是幻觉 |
| Q2 | /docs 白屏 | **0 / 4 · 幻觉** | 4 / 4 | ①答成 Spring Security 白名单 |
| Q3 | 初始数据 | **1 / 4 · 幻觉** | 4 / 4 | ①只对「3 条」，名字全编 |
| Q4 | 空格 name | 2 / 3 | 3 / 3 | ①状态码对、`detail` 编了 |
| Q5 | 依赖版本 | 0 / 4 | 4 / 4 | ①诚实拒答 |
| Q6 | ReAct 边界 | **1 / 4 · 幻觉** | 3 / 4 | ①兜底文案与 `steps` 语义都编；②少「fallback 当答案」一点 |
| Q7 | Express vs FastAPI | **0 / 4 · 幻觉** | 4 / 4 | ①把 Express 版说成内存存储（真值 SQLite） |
| Q8 | 语料纠错 | 1 / 3 | 2 / 3 | ①也会，**区分度低** |
| Q9 | 拒答（数据库） | **0 / 4 · 幻觉** | 4 / 4 | ①编出 SQLite+SQLAlchemy+表字段 |
| Q10 | 模型名/端点 | **0 / 4 · 幻觉** | 4 / 4 | ①编 `OPENAI_API_KEY` 那套 |

## 幻觉清单（6 题，全部在条件①）

| 题 | 它编了什么 | 真值 |
|---|---|---|
| Q2 | 「安全配置放行静态资源 / 放行 `/v2/api-docs`、`/v3/api-docs`」 | `FastAPI(docs_url=None)` + 自定义 `/docs` + 本地 `swagger-ui-bundle.js` / `swagger-ui.css` |
| Q3 | 三条待办：「学习 FastAPI / 写一个 TODO 应用 / 部署到服务器」 | 「学 Express(完成) / 接前端 / 学 Python + FastAPI」 |
| Q6 | 兜底文案「未能得出最终答案」；`steps` 是「带 thought/action/observation 的轨迹列表」 | 「（已达到最大步数仍未给出最终答案）」；`steps` 是整数 `len(trace)` |
| Q7 | 「Express 版数据通常存在进程内存」 | `server.js` 用 `node:sqlite` 写 `todos.db`，重启不丢 |
| Q9 | 「SQLite（SQLAlchemy，`sqlite:///./todos.db`），字段 id/title/description/completed」 | `main.py` 里 `todos` 是模块级内存 list，**没有数据库** |
| Q10 | 「`OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`」 | `DEEPSEEK_API_KEY`、`deepseek-chat`、`https://api.deepseek.com` |

## 判分口径（后续 RAG 评测沿用，别改）

1. **题目等权**：先算每题得分率 `points_hit / points_total`，再对 10 题取平均。不把要点混在一起除（否则 Q1 的 9 个要点权重是 Q4 的 3 倍）。
2. **幻觉一票否决**：出现语料中不存在的断言 → `hallucination = true`，该题记 0 分（`points_hit` 仍保留原始命中数，便于回看）。
3. **Q9 单独判定**：必须纠正前提（「没有数据库、是内存 list」）；答成 SQLite 或编表结构 = 0 分。
4. **部分命中按要点计**，不四舍五入（如 Q4 的 `detail` 错 → 2/3）。
5. 条件①② 的 `retrieved` / `hit@3` 保持 `null` —— 那是条件③（RAG）才填的字段。

## 从这份 baseline 得到的四条判断

1. **上限已量出来**：9.42 / 10。RAG 的目标不是「比 1 分高」，而是**逼近 9.4 且幻觉保持 0**。
2. **裸考的失败模式是编，不是不会**：10 题里 6 题编造、2 题老实拒答、2 题半对 → 优化方向是「压幻觉」，不是「让模型更敢答」。
3. **Q8 区分度低**：条件①也能拿分（模型本身知道 `startsWith`）。算总分时可降权或单列，别让它稀释「资料有没有用」的信号。
4. **Q7 / Q9 是高危题**：它们考「相邻实现串味」。全上下文时都对；一旦 RAG 只召回一个文件，这两题最先掉 —— 它们是检索质量的探针。

## 复现

```powershell
$env:DEEPSEEK_API_KEY="<your key>"
.\.venv\Scripts\python.exe evals\run_baseline.py
.\.venv\Scripts\python.exe evals\run_baseline.py --conditions fullctx --out evals\try.jsonl
```

产出三件套：`baseline-<commit>-<日期>.jsonl`（原始回答 + 打分）、`.manifest.json`（版本/模型/参数）、`render_answers.py` 生成的阅读稿 `.md`。

## 下一步

1. 冻结这份 baseline（提交 git，`baseline: 218e53a · noctx 1.00 / fullctx 9.42`）；
2. 重写 `/agent-raw` 的解析与循环；`todos` → SQLite（参考 `react/todo-api/server.js`）；3 条冒烟测试 + 记录 usage；
3. 上 Chroma：跑条件③，和 ② 比「分数差多少、输入 token 从 6.9k 降到多少」。

## 评分修订记录（2026-10-17）

初判有 4 处与「幻觉一票否决 / 部分命中」的口径不一致，已按下列结果修订：

| 题 | 初判 | 修订 | 理由 |
|---|---|---|---|
| Q2 noctx | 3 / 4 | **0 / 4 · 幻觉** | 答案整段是 Spring Security 的白名单，本仓库没有任何一条对得上 |
| Q4 noctx | 3 / 3 | **2 / 3** | `detail` 写成 `Todo name cannot be empty`，真值是 `name 不能为空` |
| Q6 noctx | 4 / 4 | **1 / 4 · 幻觉** | 兜底文案、`steps` 语义均为编造（只有 `max_steps=5` 碰巧对） |
| Q8 fullctx | 1 / 3 | **2 / 3** | 已指出「资料里写成 `startWith()`，缺末尾 s」，即命中「记为笔误」 |

> 另：Q2 / fullctx 原始行曾有 `"points_hit": ,` 的 JSON 语法错误（会导致整行被统计吞掉），已修复，分母统一为 4。

## 数据核对备注

- 时间戳与 `latency_ms` 逐行对得上（相邻 timestamp 的间隔 ≈ 该题耗时）。
- 两个条件的延迟总和恰好都是 15,725 ms（均值 1,572 ms）—— 数值巧合，不影响分数结论；若以后要用延迟做对比，建议先复跑一轮确认。
- 20 行全部通过 JSON 解析；每题两个条件的分母一致。
