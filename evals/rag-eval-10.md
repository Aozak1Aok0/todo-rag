# RAG 评估集（10 题 · v0.2）

> 2026-10-16 起草（Codex 会话）；**2026-10-18 升 v0.2**（SQLite 迁移后改 Q7、换 Q9）。定稿后不再改动，保证 baseline 可比。
> **本文件只给题与判分锚点。**

## 0. 这套题要回答什么问题

同一套题、同一套打分，在三种条件下各跑一次：

| 条件 | 含义 | 期望 |
|---|---|---|
| ① 不给上下文 | 纯靠模型记忆 | 下限（应该很差） |
| ② 全文塞进 prompt | 长上下文天花板 | 上限（内容全给） |
| ③ RAG 检索后回答 | 本项目实现 | 越接近 ② 越好 |

题目**全部取材于本仓库 `corpus/` 目录**（评测语料快照），所以「模型事先读过」这件事基本可以排除：不靠上下文就能答对的题，说明题出错了。

**语料版本锚点**：数据层迁移到 SQLite 之后的提交，分支 `pa`，2026-10-18。`commit: dad0e13`（提交后把 hash 填进来，baseline v2 必须锚在它上面）。
v0.1 锚定在 `218e53a「1015」`（内存 list 版）—— 那份 baseline（`baseline-218e53a-*`）只能当历史对照，别拿来比新代码。
⚠️ 以后只要动数据层/接口，就要同步检查 Q1 / Q3 / Q4 / Q7 / Q9 / Q10 的 gold 是否还成立；不成立就升版本 + 重跑 baseline。两件事别混着做。

## 1. 建议的 RAG 入库语料

范围：`corpus/` 下的文本文件，**排除** `node_modules\`、`dist\`、`*package-lock.json`、`.venv\`、`static\`（swagger 大文件）—— 总量 15 个文件 / 约 27 KB（2026-10-18 核对），正适合 Chroma 起步。

| 类别 | 文件 | 备注 |
|---|---|---|
| 主代码 | `python\fastapi-api\main.py`（328 行，SQLite 版）、`requirements.txt` | 被考察的主体 |
| 对照代码 | `react\todo-api\server.js`、`react\todo-api\package.json` | 两边现在**都用 SQLite**：Express 用 `node:sqlite` 的 `DatabaseSync`，FastAPI 用标准库 `sqlite3`；库文件同名 `todos.db`、表结构相同，但**种子数据与接口仍有差异**（Q7 的考点） |
| 其它代码 | `Express\hellonode.js`、`Express\new\myapp\index.js` | 小样例 |
| 笔记 | `note\JS.txt`、`python\prac\points.essential.txt`、`python\prac\Myworld.py` | Q8 的考点在这儿 |
| 页面/数据 | `Css.html`、`0925\superheroes.json`、`content\verse1~4.txt`、仓库根 `README.md` | 干扰项（保证检索不是「随便抓一个都对」） |

## 2. 十道题

每题四件事：**问题** / **期望要点**（打分锚点）/ **必须命中的来源**（算 hit@k 用）/ **判分说明**。
题型分布：事实型 4 · 代码推理 1 · 机制多跳 1 · 跨文件比较 1 · 语料纠错 1 · 拒答 1 · 防串味 1。

### Q1 事实型 · 路由全清单
**问**：这个 FastAPI 服务对外一共暴露了哪些路由？（含非业务路由）
**期望要点**：① `GET /docs`（自托管 Swagger）② `GET /` ③ `GET /api/todos` ④ `POST /api/todos`（201）⑤ `DELETE /api/todos/{todo_id}` ⑥ `POST /chat`（SSE 流式）⑦ `POST /agent`（SDK function calling）⑧ `POST /agent-raw`（手写 ReAct）；另挂载 `GET /static/*`。
**来源**：`pra/python/fastapi-api/main.py`
**判分**：漏一个扣分；编出 `/agent/tools` 之类不存在的路由 = 幻觉，本题 0 分。

### Q2 事实型 · /docs 白屏的修法
**问**：Swagger 页面白屏是怎么解决的？技术上做了哪两件事？
**期望要点**：① 原因是默认 `/docs` 依赖境外 CDN，国内加载白屏；② `FastAPI(docs_url=None)` 关掉默认 docs，自己写 `@app.get("/docs")` 用 `get_swagger_ui_html(...)` 指向本地 `swagger_js_url=/static/swagger-ui-bundle.js`、`swagger_css_url=/static/swagger-ui.css`；③ `app.mount("/static", StaticFiles(...))` 提供这些文件。
**来源**：`pra/python/fastapi-api/main.py`
**判分**：只答「下载到本地」不给满分，必须说出 `docs_url=None` + 自定义路由 + 静态挂载。

### Q3 事实型（精确）· 初始数据
**问**：这个 FastAPI 服务启动时 `todos` 里有哪些数据？各自的完成状态？
**期望要点**：3 条 —— `1 学 Express`（`completed: True`）、`2 接前端`（`False`）、`3 学 Python + FastAPI`（`False`）。
**来源**：`pra/python/fastapi-api/main.py`
**判分**：数字要 3；名称与状态都要对；**第三条答成「学 SQLite」= 串到 Express 版去了**（见 `server.js` 的种子数据），扣满。

### Q4 代码推理 · 边界输入
**问**：`POST /api/todos`，body 是 `{"name": "   "}`（三个空格）。返回什么？为什么不是 422？
**期望要点**：① **400**，`detail` 为 `name 不能为空`；② 原因是 `todo.name.strip()` 后判空并主动 `raise HTTPException(400)`；③ 422 是 pydantic 校验失败（类型/缺字段）才用，这里类型合法，是业务规则没过。
**来源**：`pra/python/fastapi-api/main.py`
**判分**：答 422 = 0 分（把校验层搞混了）；只答 400 不说原因给一半。

### Q5 事实型（精确）· 依赖版本
**问**：`requirements.txt` 锁了哪几个包、什么版本？
**期望要点**：`fastapi==0.143.0`、`uvicorn==0.54.0`、`httpx==0.28.1`、`openai==3.29.0`（4 个都要）。
**来源**：`pra/python/fastapi-api/requirements.txt`
**判分**：版本号错一位就扣；写「最新版」= 0 分。

### Q6 机制多跳 · ReAct 循环的边界
**问**：手写 ReAct 循环最多跑几步？达到上限还没输出 Final Answer 时会返回什么？返回体里的 `steps` 是什么？
**期望要点**：① `max_steps=5`（`_run_react` 默认参数）；② 未拿到答案时 `answer` 兜底为固定文案「（已达到最大步数仍未给出最终答案）」；③ `steps = len(trace)`，trace 每步一条，类型有 `action` / `final` / `fallback`；④ 顺带：模型既没给 Action 也没给 Final Answer 时走 fallback —— 把原文当答案。
**来源**：`pra/python/fastapi-api/main.py`
**判分**：③④ 是加分点（能看出真读过循环）；只答 5 步给一半。

### Q7 跨文件比较 · Express vs FastAPI
**问**：Express 版 todo（`react\todo-api\server.js`）和 FastAPI 版（`main.py`）在「数据层实现」和「接口」上有什么不同？
**期望要点**：① 两边都用 SQLite，但实现不同：Express 用 `node:sqlite` 的 `DatabaseSync`；FastAPI 用标准库 `sqlite3`，**每次操作新开连接**。② 库文件都叫 `todos.db`，表结构相同：`todos(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, completed INTEGER DEFAULT 0)`。③ 种子数据第三条不同：Express 是「学 SQLite」，FastAPI 是「学 Python + FastAPI」（前两条一样）。④ 接口差异：Express 有 `PATCH /api/todos/:id`（切完成状态）、`DELETE` 返回 204；FastAPI 没有 PATCH、`DELETE` 返回 200 + `{"msg","id"}`，另有 `/chat`、`/agent`、`/agent-raw`、`/docs`。
**来源**：`pra/react/todo-api/server.js` + `pra/python/fastapi-api/main.py`（**两个都要命中**）
**判分**：多跳题 —— 只检索到一个文件必然答不全；说「FastAPI 还在用内存 list」= 过时答案，0 分。

### Q8 语料纠错 · 别照抄错笔记
**问**：`note\JS.txt` 里写「`startWith()`：判断字符串是否以指定子字符串开头」。这个 API 名对吗？
**期望要点**：① **不对**，正确拼写是 `startsWith()`；② 笔记这里是笔误；③ 正确用法 `str.startsWith(prefix)` 返回 boolean，与 `endsWith()` 对称。
**来源**：`pra/note/JS.txt`
**判分**：**照抄笔记说「对的」= 0 分**（考点就是别盲信检索结果）；指出笔误并给出正解 = 满分。

### Q9 拒答型（必须承认语料里没有）
**问**：`todos` 表里有没有 `created_at`、`due_date` 或用户相关字段？这个服务支持多用户吗？
**期望要点**：正确行为是**纠正前提**：表里只有 `id` / `name` / `completed` 三列，**没有** `created_at`、`due_date`，也没有用户字段或用户表；没有鉴权，所有请求共用同一份待办列表 → **不支持多用户**。
加分：指出要支持多用户得加 `user_id` 外键 + 鉴权（当前没做）。
**来源**：`pra/python/fastapi-api/main.py`（`init_db()` 的建表语句是唯一权威）
**判分**：编出 `created_at` / `due_date` / `user_id` / `users` 表 = **幻觉，0 分**。考点是「按 DDL 说话、不按常识脑补」—— 大多数 TODO 教程都有 `created_at`，这里**恰好没有**。

### Q10 防串味 · 模型名与端点
**问**：调用大模型时用的模型名、`base_url`、key 从哪来？key 缺失会怎样？
**期望要点**：① `model="deepseek-chat"`；② `AsyncOpenAI(base_url="https://api.deepseek.com")`；③ key 读环境变量 `DEEPSEEK_API_KEY`，缺失时 `get_client()` 直接 500，`detail` 为「未设置 DEEPSEEK_API_KEY 环境变量」。
**来源**：`pra/python/fastapi-api/main.py`
**判分**：`deepseek-flash` / `api.deepseek.com/v1` 是**本机 Codex CLI 侧**的配置，跟这个服务无关 —— 混进来扣满。（专门测上下文串味。）

## 3. 怎么打分

| 层 | 指标 | 说明 |
|---|---|---|
| 检索 | hit@3、MRR | 用每题 `gold_sources` 标注；命中即 1 |
| 答案 | 要点覆盖率 | 命中要点数 ÷ 要点总数（人工或 LLM-judge 逐条判） |
| 答案 | **幻觉一票否决** | 出现语料中不存在的断言（编路由/编表结构/编版本）→ 该题 0 分 |
| 拒答 | Q9 单独看 | 编造 `created_at` / 用户字段 = 0；明确「只有 id/name/completed、无多用户」= 1 |
| 运行 | latency_ms / tokens(in,out) / 成本 | 每题都记 |

通过线（建议）：
- 条件①（无 RAG）预期 ≤ 2/10 ——**这个低分是正常的，它就是 baseline**；
- 加 RAG 后目标 ≥ 7/10，且**幻觉 0 次**、Q9 满分。

### 结果行格式（一题一行 JSONL，先定好，脚本才好写）

```json
{"id":"Q1","eval_version":"0.2","condition":"rag","retrieved":["pra/python/fastapi-api/main.py"],"hit@3":1,"points_hit":6,"points_total":9,"hallucination":false,"answer":"...","latency_ms":1840,"tokens_in":2100,"tokens_out":180,"cost_usd":0.0004}
```

## 4. 建议顺序（别跳）

1. **先把 baseline 跑下来并存档**（条件 ① ②）——现在代码已包含 SQLite 迁移，跑之前先确认 `corpus.txt` 与 gold 都是 v0.2；
2. ~~SQLite 迁移~~（已完成 2026-10-18：SQLite + 5 条冒烟测试 + 真重启 e2e）；
3. 上 Chroma 做 RAG（`embed.py` 的本地 bge 模型已就位），跑条件 ③，和 ② 比差多少；
4. 每次动数据层/接口 → 先检查 gold、必要时升版本并重跑 baseline，别拿旧 baseline 比新代码。

## 5. 变更记录

| 版本 | 日期 | 改动 |
|---|---|---|
| v0.1 | 2026-10-16 | 初始 10 题（锚定 `218e53a`，内存 list 版） |
| v0.2 | 2026-10-18 | SQLite 迁移后：Q7 改为「两边都用 SQLite，差异在种子数据与接口」；Q9 原题（「没有数据库」）前提失效 → 换成「有没有 created_at/due_date/用户字段、是否支持多用户」；语料版本锚点与建议顺序同步更新。**v0.1 的 baseline 只作历史对照。** |

## 6. v0.3 变更（2026-10-26）

数据层迁到 `store.py` 后，Q3 / Q7 / Q9 的 gold 补上 `pra/python/fastapi-api/store.py`
（建表语句、SEEDS、init_db 都在这里，main.py 只调用）。题目与判分锚点不变。
