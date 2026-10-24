# 回答阅读稿：baseline-dad0e13-20261018.jsonl

> commit `dad0e13` · 分支 `pa` · 模型 `deepseek-chat` temp=0.0 · 条件 ['noctx', 'fullctx'] · 生成于 2026-10-18T13:33:09

> 本文件仅供阅读；打分层字段请你在 scorer 里填。

---

## Q1 · fact · 难度 1

**问题**：这个 FastAPI 服务对外一共暴露了哪些路由（含非业务路由）？

**你的打分锚点（expected_points）**：
- 1. GET /docs（自托管 Swagger）
- 2. GET /
- 3. GET /api/todos
- 4. POST /api/todos（201）
- 5. DELETE /api/todos/{todo_id}
- 6. POST /chat（SSE 流式）
- 7. POST /agent（SDK function calling）
- 8. POST /agent-raw（手写 ReAct）
- 9. /static 静态挂载

**gold_sources**：pra/python/fastapi-api/main.py

**判分说明**：编造不存在的路由=幻觉，本题 0 分

### 条件① 无上下文（纯靠模型记忆）  <sub>`1754ms` · in=39 out=176 · err=None</sub>

我无法直接查看你的代码库内容，因此不能准确列出该 FastAPI 服务实际暴露的全部路由。  

要得到完整清单（含非业务路由），可以：

1. 查看应用实例的 `app.routes`，例如：
```python
for r in app.routes:
    print(getattr(r, "methods", None), getattr(r, "path", None), getattr(r, "name", None))
```
2. 或启动服务后访问 `/openapi.json`，查看 `paths` 字段。
3. 注意 FastAPI 默认还会暴露：
   - `/openapi.json`
   - `/docs`
   - `/docs/oauth2-redirect`
   - `/redoc`

如果你把 `main.py` 或路由注册相关代码贴出来，我可以帮你逐条整理成完整路由清单。

### 条件② 全文塞进 prompt（上限）  <sub>`1879ms` · in=7192 out=260 · err=None</sub>

根据资料，FastAPI 服务（`python/fastapi-api/main.py`）暴露的路由如下：

**非业务路由**
- `GET /docs` —— 自定义 Swagger UI（`include_in_schema=False`）
- `/static` —— 静态文件挂载（`app.mount`，用于 swagger 资源）
- `GET /` —— 根路由，返回 `{"msg": "Todo + LLM API 运行中"}`

**待办业务路由**
- `GET /api/todos` —— 列出全部待办
- `POST /api/todos` —— 新增待办（201）
- `DELETE /api/todos/{todo_id}` —— 删除待办

**大模型相关路由**
- `POST /chat` —— 多轮流式对话（SSE）
- `POST /agent` —— Function Calling 版 Agent
- `POST /agent-raw` —— 手写 ReAct 版 Agent

另外，FastAPI 默认的 `/openapi.json` 由 `app.openapi_url` 提供（代码中 `get_swagger_ui_html` 引用了它），但资料未显式声明该端点，仅可推断其存在。

---

## Q2 · fact · 难度 2

**问题**：Swagger 页面白屏是怎么解决的？技术上做了哪两件事？

**你的打分锚点（expected_points）**：
- 1. 原因是默认 /docs 依赖境外 CDN，国内白屏
- 2. FastAPI(docs_url=None) 关掉默认 docs
- 3. 自定义 @app.get("/docs") 用 get_swagger_ui_html 指向本地 js/css
- 4. app.mount("/static", StaticFiles(...)) 提供 swagger-ui-bundle.js 与 swagger-ui.css

**gold_sources**：pra/python/fastapi-api/main.py

**判分说明**：只说“下载到本地”不给满分

### 条件① 无上下文（纯靠模型记忆）  <sub>`1541ms` · in=36 out=172 · err=None</sub>

Swagger 页面白屏的解决方式是：**升级 Swagger 相关依赖版本**，并**调整安全配置放行 Swagger 资源路径**。

技术上做了两件事：

1. **升级依赖**：将 Swagger（如 springfox / springdoc）相关依赖升级到兼容当前 Spring Boot 版本的版本，解决因版本不匹配导致的页面资源加载失败、白屏问题。
2. **放行安全路径**：在安全配置（如 Spring Security 的过滤链）中，将 Swagger 的静态资源与接口路径（如 `/swagger-ui/**`、`/v3/api-docs/**`、`/swagger-resources/**`、`/webjars/**` 等）加入白名单，允许匿名访问，避免被安全拦截导致页面无法加载。

### 条件② 全文塞进 prompt（上限）  <sub>`1552ms` · in=7189 out=179 · err=None</sub>

资料中给出的解决方式是：**不用 FastAPI 默认的 /docs，改为自定义 /docs 页面并加载本地静态资源**。

技术上做了两件事：

1. **禁用默认 /docs 端点**：`app = FastAPI(docs_url=None)`。
2. **自定义 /docs 路由，改用本地 Swagger 资源**：通过 `get_swagger_ui_html(...)` 返回页面，并把 `swagger_js_url` 指向 `/static/swagger-ui-bundle.js`、`swagger_css_url` 指向 `/static/swagger-ui.css`；同时用 `app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")` 把本地 `static` 目录挂载到 `/static`，从而不再依赖外部 CDN，解决国内访问白屏问题。

---

## Q3 · fact-exact · 难度 1

**问题**：这个 FastAPI 服务启动时 todos 里有哪些数据？各自的完成状态？

**你的打分锚点（expected_points）**：
- 1. 共 3 条
- 2. 1 学 Express，completed=true
- 3. 2 接前端，completed=false
- 4. 3 学 Python + FastAPI，completed=false

**gold_sources**：pra/python/fastapi-api/main.py

**判分说明**：第三条答“学 SQLite”=串到 Express 版（server.js 种子数据）去了，扣满

### 条件① 无上下文（纯靠模型记忆）  <sub>`1129ms` · in=38 out=95 · err=None</sub>

根据代码库中的初始化数据，服务启动时 `todos` 里有 3 条数据：

1. **id=1**：`"Buy groceries"` —— 未完成（`completed=False`）
2. **id=2**：`"Walk the dog"` —— 未完成（`completed=False`）
3. **id=3**：`"Read a book"` —— 已完成（`completed=True`）

### 条件② 全文塞进 prompt（上限）  <sub>`1368ms` · in=7191 out=106 · err=None</sub>

根据 `python/fastapi-api/main.py` 中的 `init_db()`：当 `todos` 表为空时，会插入三条默认数据：

1. **学 Express** — 已完成（completed = 1）
2. **接前端** — 未完成（completed = 0）
3. **学 Python + FastAPI** — 未完成（completed = 0）

注意：只有在表为空时才会插入这些种子数据；如果数据库里已有记录，则不会重复插入。

---

## Q4 · code-reasoning · 难度 3

**问题**：POST /api/todos，body 为 {"name": "   "}（三个空格）：返回什么？为什么不是 422？

**你的打分锚点（expected_points）**：
- 1. HTTP 400，detail 为 name 不能为空
- 2. 原因：name.strip() 后判空并 raise HTTPException(400)
- 3. 422 只用于 pydantic 校验失败（类型/缺字段），此处类型合法

**gold_sources**：pra/python/fastapi-api/main.py

**判分说明**：答 422 = 0 分

### 条件① 无上下文（纯靠模型记忆）  <sub>`1475ms` · in=49 out=157 · err=None</sub>

返回 **400 Bad Request**（通常 body 类似 `{"detail": "Todo name cannot be empty"}`），而不是 422。

原因：

- 该接口对 `name` 做了**业务层校验**：先 `strip()` 去掉首尾空白，再判断是否为空。`"   "` strip 后是空字符串，因此主动抛出 400。
- 422 是 FastAPI/Pydantic 的**请求体结构校验**错误（字段缺失、类型不对等）。这里 `name` 是合法字符串，能通过 Pydantic 解析，所以不会触发 422。
- 空/纯空白属于**语义无效**而非结构无效，项目约定用 400 表达，因此返回 400。

### 条件② 全文塞进 prompt（上限）  <sub>`1250ms` · in=7202 out=160 · err=None</sub>

**返回：** `400`，响应体为 `{"detail": "name 不能为空"}`。

**原因：** 在 `create_todo` 中，先执行 `name = todo.name.strip()`，三个空格被 strip 成空字符串，随后 `if not name:` 成立，抛出 `HTTPException(status_code=400, detail="name 不能为空")`。

**为什么不是 422：** 422 是 Pydantic 校验失败时的状态码。`TodoCreate` 模型里 `name: str` 只要求是字符串，`"   "` 是合法字符串，能通过模型校验，所以不会触发 422。空值判断是在进入函数后手动做的业务校验，因此返回 400。

---

## Q5 · fact-exact · 难度 1

**问题**：requirements.txt 锁了哪几个包、什么版本？

**你的打分锚点（expected_points）**：
- 1. fastapi==0.143.0
- 2. uvicorn==0.54.0
- 3. httpx==0.28.1
- 4. openai==3.29.0

**gold_sources**：pra/python/fastapi-api/requirements.txt

**判分说明**：版本号错一位即扣分；答“最新版”= 0 分

### 条件① 无上下文（纯靠模型记忆）  <sub>`1437ms` · in=33 out=60 · err=None</sub>

我先看一下仓库里的 `requirements.txt`。

当前对话里没有提供该文件内容，我也无法直接读取代码库，因此不能确认具体锁了哪些包和版本。请把 `requirements.txt` 内容贴出来，或允许我访问仓库文件，我再帮你逐项列出。

### 条件② 全文塞进 prompt（上限）  <sub>`879ms` · in=7186 out=61 · err=None</sub>

资料中 `python/fastapi-api/requirements.txt` 锁定了 4 个包：

- fastapi==0.143.0
- uvicorn==0.54.0
- httpx==0.28.1
- openai==3.29.0

---

## Q6 · mechanism-multihop · 难度 3

**问题**：手写 ReAct 循环最多跑几步？到上限仍无 Final Answer 时返回什么？返回里的 steps 是什么？

**你的打分锚点（expected_points）**：
- 1. max_steps=5（_run_react 默认参数）
- 2. 兜底文案：（已达到最大步数仍未给出最终答案）
- 3. steps = len(trace)，每步一条，类型含 action/final/fallback
- 4. 既无 Action 也无 Final Answer 时走 fallback：把原文当答案

**gold_sources**：pra/python/fastapi-api/main.py

**判分说明**：后两条是加分点

### 条件① 无上下文（纯靠模型记忆）  <sub>`1217ms` · in=48 out=126 · err=None</sub>

手写 ReAct 循环默认最多跑 **5 步**（`max_steps=5`）。

到上限仍无 Final Answer 时，返回一个兜底结果，其中 `answer` 为固定提示语（类似“达到最大步数仍未得到最终答案”），并标记 `finished=False`（或等价的未完成标志）。

返回里的 `steps` 是**执行轨迹列表**：每一步记录该轮的思考/动作/观察（如 `thought`、`action`、`action_input`、`observation`），用于回放和调试整个 ReAct 过程。

### 条件② 全文塞进 prompt（上限）  <sub>`1170ms` · in=7201 out=113 · err=None</sub>

根据资料：

- **最多跑几步**：`_run_react` 的 `max_steps` 默认值为 **5**，即最多循环 5 步。
- **到上限仍无 Final Answer 时返回什么**：返回 `"（已达到最大步数仍未给出最终答案）"` 作为 answer。
- **返回里的 steps 是什么**：`steps` 是 `len(trace)`，即记录下来的每一步轨迹条数（trace 里记录了 final / action / fallback 等步骤）。

---

## Q7 · cross-file-compare · 难度 3

**问题**：Express 版 todo（react/todo-api/server.js）与 FastAPI 版（main.py）在「数据层实现」和「接口」上有什么不同？

**你的打分锚点（expected_points）**：
- 1. 两边都用 SQLite，但实现不同：Express 用 node:sqlite 的 DatabaseSync；FastAPI 用标准库 sqlite3，每次操作新开连接
- 2. 库文件都叫 todos.db，表结构相同：todos(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, completed INTEGER DEFAULT 0)
- 3. 种子数据第三条不同：Express 是「学 SQLite」，FastAPI 是「学 Python + FastAPI」（前两条相同）
- 4. 接口差异：Express 有 PATCH /api/todos/:id、DELETE 返回 204；FastAPI 没有 PATCH、DELETE 返回 200 + {msg,id}，另有 /chat /agent /agent-raw /docs

**gold_sources**：pra/react/todo-api/server.js、pra/python/fastapi-api/main.py

**判分说明**：多跳题：两个文件都要命中；说「FastAPI 还在用内存 list」= 过时答案，0 分

### 条件① 无上下文（纯靠模型记忆）  <sub>`3133ms` · in=56 out=562 · err=None</sub>

# Express 版 vs FastAPI 版 todo 对比

## 一、数据层实现

| 维度 | Express（server.js） | FastAPI（main.py） |
|---|---|---|
| 存储方式 | 内存数组（如 `let todos = []`），进程重启即丢失 | 通常用 SQLite/SQLAlchemy 或内存列表，视实现而定 |
| 数据模型 | 无显式模型，直接操作 JS 对象 `{id, text, done}` | 用 Pydantic 模型（如 `TodoCreate`、`Todo`）做校验与序列化 |
| ID 生成 | 手动维护自增计数器或 `Date.now()` | 数据库自增主键或 `uuid` |
| 校验 | 基本无校验，靠手写 if 判断 | Pydantic 自动类型/字段校验，非法请求返回 422 |
| 持久化 | 无 | 若接数据库则有持久化 |

## 二、接口层面

| 维度 | Express | FastAPI |
|---|---|---|
| 路由定义 | `app.get('/todos', ...)` 等 Express 风格 | `@app.get("/todos")` 装饰器 + 路径操作函数 |
| 请求体解析 | `express.json()` 中间件 + `req.body` | 函数参数声明 Pydantic 模型，自动解析 |
| 响应 | `res.json(...)` 手动返回 | 直接 `return` 对象/列表，自动序列化 |
| 参数校验 | 手动 | 自动，错误格式统一 |
| 文档 | 无（需额外 swagger 配置） | 自动生成 OpenAPI/Swagger（`/docs`） |
| 异步 | 回调/Promise | `async def` 原生支持 |
| 错误处理 | 手动 `res.status(404).json(...)` | `raise HTTPException(status_code=404, ...)` |

## 三、核心差异总结

1. **类型与校验**：FastAPI 靠 Pydantic 声明式校验，Express 靠手写逻辑。
2. **文档**：FastAPI 自带交互式 API 文档，Express 需额外集成。
3. **数据层抽象**：FastAPI 通常配合 ORM（SQLAlchemy）形成模型层；Express 版多为裸内存数组，无模型抽象。
4. **错误与状态码**：FastAPI 用异常机制统一处理；Express 需在每个 handler 里手动设置。

> 注：具体细节取决于两个文件的实际代码，以上为典型实现差异。如需逐行对照，可提供文件内容。

### 条件② 全文塞进 prompt（上限）  <sub>`2517ms` · in=7209 out=546 · err=None</sub>

**数据层实现**

- Express 版（`react/todo-api/server.js`）：使用 `node:sqlite` 的 `DatabaseSync`，数据库文件固定为 `"todos.db"`（相对路径，不可配置）；建表、种子数据、增删改查全部用 `db.prepare(...).run/get/all` 同步执行。
- FastAPI 版（`main.py`）：使用 Python 标准库 `sqlite3`，数据库路径由环境变量 `TODO_DB` 决定，默认 `BASE_DIR / "todos.db"`；每次操作都新建连接、`try/finally` 关闭，查询时用 `row_factory = sqlite3.Row` 转字典，`completed` 的 0/1 转成 `bool`。

**接口**

- Express 版：
  - `GET /api/todos`（列表）
  - `POST /api/todos`（新增，201）
  - `DELETE /api/todos/:id`（删除，成功返回 204，找不到 404）
  - `PATCH /api/todos/:id`（切换完成状态，要求 `completed` 为布尔值）
  - `GET /`（返回文本 "Todo API 运行中"）
- FastAPI 版：
  - `GET /api/todos`（列表）
  - `POST /api/todos`（新增，201）
  - `DELETE /api/todos/{todo_id}`（删除，成功返回 `{"msg": "deleted", "id": ...}`，找不到 404）
  - `GET /`（返回 JSON `{"msg": "Todo + LLM API 运行中"}`）
  - 额外还有 LLM 相关接口：`POST /chat`（SSE 流式）、`POST /agent`（Function Calling）、`POST /agent-raw`（手写 ReAct），以及自定义 `/docs`。

**主要差异归纳**

1. Express 有 `PATCH` 切换完成状态接口，FastAPI 版没有。
2. 删除成功时 Express 返回 204 无内容，FastAPI 返回 200 + JSON。
3. FastAPI 版多了大模型对话/Agent 接口和自定义 Swagger 文档，Express 版没有。
4. 数据库路径：Express 写死，FastAPI 可用 `TODO_DB` 环境变量配置。
5. 种子数据内容略有不同：Express 第三条是「学 SQLite」，FastAPI 是「学 Python + FastAPI」。

---

## Q8 · corpus-trap · 难度 2

**问题**：note/JS.txt 里写的 startWith() 这个 API 名对吗？

**你的打分锚点（expected_points）**：
- 1. 不对，正确拼写是 startsWith()
- 2. 属性记为笔误
- 3. 用法 str.startsWith(prefix) 返回 boolean，与 endsWith() 对称

**gold_sources**：pra/note/JS.txt

**判分说明**：照抄笔记说“对”= 0 分（考点是不盲信检索结果）

### 条件① 无上下文（纯靠模型记忆）  <sub>`825ms` · in=38 out=21 · err=None</sub>

不对。正确的方法是 `startsWith()`（带 s），`startWith()` 不是标准 API。

### 条件② 全文塞进 prompt（上限）  <sub>`917ms` · in=7191 out=47 · err=None</sub>

不对。资料中 `note/JS.txt` 写的是 `startWith()`，但正确的 JavaScript 字符串方法名是 `startsWith()`（资料里写成了 `startWith`，少了结尾的 `s`）。

---

## Q9 · must-refuse · 难度 3

**问题**：todos 表里有没有 created_at、due_date 或用户相关字段？这个服务支持多用户吗？

**你的打分锚点（expected_points）**：
- 1. 纠正前提：表里只有 id / name / completed 三列，没有 created_at、due_date
- 2. 没有用户字段或用户表，也没有鉴权
- 3. 所有请求共用同一份待办列表 → 不支持多用户
- 4. 加分：要支持多用户需加 user_id 外键 + 鉴权（当前没做）

**gold_sources**：pra/python/fastapi-api/main.py  ·  **本题必须拒答**

**判分说明**：编出 created_at/due_date/user_id/users 表 = 幻觉 0 分。考点：按 DDL 说话，不按常识脑补

### 条件① 无上下文（纯靠模型记忆）  <sub>`1299ms` · in=45 out=123 · err=None</sub>

根据当前代码库，我无法确认 `todos` 表的具体字段，也无法确认该服务是否支持多用户——代码库中没有找到相关的表结构定义或用户/鉴权相关代码。

建议你：
1. 查看数据库迁移文件或 schema 定义（如 `migrations/`、`schema.sql`、ORM 模型文件）确认 `todos` 表字段；
2. 搜索 `user_id`、`auth`、`session` 等关键词判断是否有用户体系。

如果你能提供具体的 schema 文件或模型代码，我可以帮你进一步确认。

### 条件② 全文塞进 prompt（上限）  <sub>`1462ms` · in=7198 out=130 · err=None</sub>

资料中没有 created_at、due_date 或用户相关字段。

两个后端（`python/fastapi-api/main.py` 和 `react/todo-api/server.js`）的 todos 表都只有三个字段：

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `name TEXT NOT NULL`
- `completed INTEGER`（默认 0）

关于多用户：资料中没有体现任何多用户支持。没有用户表、没有用户 ID 字段、没有登录/鉴权逻辑，接口也不区分用户——所有请求共享同一份 todos 数据。因此按资料来看，这个服务是单用户/无用户概念的。

---

## Q10 · anti-contamination · 难度 2

**问题**：调用大模型时用的模型名、base_url、key 来源？key 缺失会怎样？

**你的打分锚点（expected_points）**：
- 1. model="deepseek-chat"
- 2. AsyncOpenAI(base_url="https://api.deepseek.com")
- 3. key 读环境变量 DEEPSEEK_API_KEY
- 4. 缺失时 get_client() 抛 500，detail 为未设置 DEEPSEEK_API_KEY 环境变量

**gold_sources**：pra/python/fastapi-api/main.py

**判分说明**：deepseek-flash / api.deepseek.com/v1 是本机 Codex CLI 侧配置，混进来扣满

### 条件① 无上下文（纯靠模型记忆）  <sub>`1665ms` · in=42 out=202 · err=None</sub>

根据代码库中的实现：

**模型名、base_url、key 的来源**

- **模型名**：来自配置项（如 `LLM_MODEL` / 环境变量），代码中读取配置后传给大模型客户端。
- **base_url**：同样来自配置（如 `LLM_BASE_URL` / 环境变量），用于指定 OpenAI 兼容接口地址。
- **key**：来自配置/环境变量（如 `LLM_API_KEY` 或 `OPENAI_API_KEY`），在初始化客户端时读取。

**key 缺失时的行为**

- 初始化客户端时若 key 为空，通常会抛出异常或直接报错（如鉴权失败 / 缺少 API key 的错误），导致调用大模型失败；具体表现为启动或首次请求时报错，而不是静默降级。

> 注：以上为基于常见实现的概括，具体变量名与报错文案以代码库中对应配置读取和客户端初始化处为准。

### 条件② 全文塞进 prompt（上限）  <sub>`1089ms` · in=7195 out=162 · err=None</sub>

根据资料（`python/fastapi-api/main.py`）：

- **模型名**：`deepseek-chat`（`/chat`、`/agent`、`/agent-raw` 三处均使用）。
- **base_url**：`https://api.deepseek.com`（在 `get_client()` 中设置）。
- **key 来源**：环境变量 `DEEPSEEK_API_KEY`，通过 `os.getenv("DEEPSEEK_API_KEY")` 读取。
- **key 缺失时**：`get_client()` 会抛出 `HTTPException(status_code=500, detail="未设置 DEEPSEEK_API_KEY 环境变量")`，即返回 500 并给出友好提示，而不是在调用处崩溃。

---
