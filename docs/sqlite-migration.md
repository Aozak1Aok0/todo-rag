# 数据层迁移清单（todos → SQLite）

> **状态：已完成（2026-10-18）** —— `tests/smoke_test.py` 5/5 通过；另做了真·重启 e2e（起两次 uvicorn 子进程、共享同一 DB，数据存活）。`main.py` 工作区已有改动待提交，`.gitignore` 已忽略 `todos.db*`。

> 2026-10-18 · 配套 `main.py`（`218e53a` 之后的版本）· 只给清单和判据，代码你写。
> 顺带说明：`embed.py` + `models/bge-small-zh-v1.5` + `chromadb` 已经就位，
> 但 **RAG 要检索的"真实数据源"正是这张待办表** —— 所以先把数据层收口。

## 0. 完成标准（Definition of Done）

- [x] 重启服务后，新加的待办**还在**（内存 list 做不到这点，这是唯一的硬指标）
- [x] 三个 CRUD 接口行为不变：状态码、字段名、空 `name` 返回 400
- [x] `/api/todos` 返回的 `completed` 仍是 **`true/false`**，不是 `0/1`
- [x] `/agent` 和 `/agent-raw` 的 `query_todos` 读到的是**库里的数据**（手动改库 → 问 agent → 回答跟着变）
- [x] 3 条冒烟测试通过，且**测试不碰真实库**

## 1. 选型：先用标准库 `sqlite3`（不加依赖）

| 方案 | 好处 | 代价 |
|---|---|---|
| **`sqlite3`（推荐先做）** | 0 依赖；看得见 SQL、事务、建表过程 | 同步 IO，在 async 路由里会阻塞事件循环（本地项目可接受） |
| `SQLModel` / SQLAlchemy | 模型即表、少写 SQL、以后加关系方便 | 多一层抽象；先学它=先学框架，不是先学数据库 |

**建议**：这次用 `sqlite3`；等你觉得"手写 SQL 太啰嗦"了，再换 SQLModel——那时你才知道它在替你做什么。
要解决阻塞，后续用 `fastapi.concurrency.run_in_threadpool(...)` 包一下即可（本次不做）。

## 2. 改造点（按依赖顺序，行号对应现在的 `main.py`）

**① 数据层：替换 44–48 行的内存 list**

- `DB_PATH` 走环境变量：`TODO_DB`，缺省 `BASE_DIR / "todos.db"` —— **必须在"调用时"读环境变量**（写成一个函数），
  否则 `import main` 的瞬间就把路径定死了，测试想换库都换不了。
- `init_db()`：建表 + **仅当表为空**时插 3 条种子（学 Express/1、接前端/0、学 Python + FastAPI/0）。
- 可选：`PRAGMA journal_mode=WAL`（并发读写更顺，单机小项目不加也行）。

**② 统一入口 `list_todos() -> list[dict]`** ← 本次最重要的重构

- 一次 SELECT，`completed` 由 `0/1` 转成 `bool`；
- 供给三处复用：`GET /api/todos`、`/agent` 的工具结果、`_run_react` 的观察结果。
- 好处：以后换库（Chroma / Postgres）只改这一个函数。

**③ `GET /api/todos`（66–68 行）** → `return list_todos()`

**④ `POST /api/todos`（71–79 行）** → INSERT

- 空 `name` 的 400 校验**留在路由层**（业务规则，不属于数据层）；
- 新 id 用 `cursor.lastrowid`，不要再写 `max(...)+1`（并发下会重复）；
- 返回 `{"id": new_id, "name": name, "completed": False}`，状态码仍 201。

**⑤ `DELETE /api/todos/{todo_id}`（82–89 行）** → DELETE

- `cursor.rowcount == 0` → 404（`detail` 保持 `"not found"`，别改接口契约）；
- 成功仍返回 `{"msg": "deleted", "id": todo_id}`。

**⑥ `/agent` 第 155 行**：`result = {"todos": todos}` → `{"todos": list_todos()}`

**⑦ `_run_react` 第 243 行**：`observation = {"todos": todos}` → `{"todos": list_todos()}`

**⑧ `.gitignore`**：加 `todos.db`、`todos.db-wal`、`todos.db-shm`（本地数据不进仓）

**⑨ `requirements.txt`**：不用改（`sqlite3` 是内置模块）

> 可选（不在本次范围）：补一个 `PATCH /api/todos/{id}` 切完成状态 —— Express 版 `server.js` 有，FastAPI 版还没有。
> 想加就作为第 4 条测试一起写。

## 3. SQL（照抄即可，注意类型）

```sql
CREATE TABLE IF NOT EXISTS todos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT    NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0      -- SQLite 没有 bool，0/1 存，出库转 bool
);

SELECT id, name, completed FROM todos ORDER BY id;
INSERT INTO todos (name, completed) VALUES (?, 0);
DELETE FROM todos WHERE id = ?;
```

## 4. 四个坑（都是会真踩到的）

1. **种子重复插入**：只在 `SELECT COUNT(*)` 为 0 时插；否则每次启动 +3 条，重启三次变 12 条。
2. **连接生命周期**：每次操作 `with sqlite3.connect(DB_PATH) as conn:` 开/关，别搞模块级单连接。
   （单连接在 TestClient 的多线程下会炸；`check_same_thread=False` 是糊，不是解。）
3. **`row_factory`**：`conn.row_factory = sqlite3.Row`，否则只能按下标取，`row["name"]` 会报错。
4. **bool 转换**：`completed` 出库是 `0/1`。忘了转，`/api/todos` 的 JSON 就变成 `0/1`（接口契约变了），
   而且 agent 的观察结果里也会是 `0/1` —— 模型可能因此答错"哪条完成了"。

## 5. 测试清单（3 必做 + 2 加分）

环境里**没装 pytest**（`httpx` 有，`TestClient` 可用）。建议照 `tests/smoke_test.py` 的样式写个普通脚本：
`tests/smoke_test.py`，用 `assert` + PASS/FAIL 汇总，零依赖。（想用 pytest 也行，先 `pip install pytest`。）

| # | 测什么 | 关键断言 | 证明了什么 |
|---|---|---|---|
| T1 | 读 | `GET /api/todos` → 200，3 条种子；`completed` 是 `bool`；每条恰好 `id/name/completed` 三个字段 | 数据层接上了、类型没变味 |
| T2 | 写 + **持久化** | `POST` → 201 且有 id；再 GET 4 条；**丢掉 app/TestClient 重新建一个（同一 DB 文件）→ 仍是 4 条** | **真落库**（内存 list 过不了这条） |
| T3 | 删 | 删已有 → 200；删不存在 → 404；删完 GET 少一条 | 404 分支没被改造弄丢 |
| T4（加分） | 业务校验没破 | `POST {"name": "   "}` → 400，`detail` 仍是 `name 不能为空` | 改造没顺手把校验也搬进库里 |
| T5（加分） | agent 读的是库 | FakeClient 喂 `Action: query_todos`，先往库里插一条新待办，断言第二次调用的 `messages` 里出现**新数据** | 工具真的查库了，不是读启动时的快照 |

**测试隔离（必须）**：
- 每个测试用独立的临时 DB：把 `TODO_DB` 指到 `tempfile.mkdtemp()` 下的文件；
- 因为 DB 路径是"调用时"读 env 的，测试里 `os.environ["TODO_DB"] = ...` 立刻生效；
- 跑完删掉临时目录，**别让测试写进 `fastapi-api/todos.db`**。

## 6. 建议的提交序列（三个小 commit，坏了能单独回滚）

```
1. feat(db): sqlite 数据层（init_db / list_todos）+ .gitignore 忽略 todos.db
2. refactor(api): CRUD 与 agent 工具改读库
3. test(sqlite): 3 条冒烟测试（含"重建客户端后数据还在"）
```

## 7. 手动验收（不看测试也能验）

```powershell
cd <repo>
$env:DEEPSEEK_API_KEY="<从凭据管理器取>"
.\.venv\Scripts\python.exe -m uvicorn main:app --reload

# 另开一个终端：
curl.exe -s http://127.0.0.1:8000/api/todos
curl.exe -s -X POST http://127.0.0.1:8000/api/todos -H "Content-Type: application/json" -d "{\"name\":\"验证持久化\"}"
# 停掉 uvicorn（Ctrl+C），再启动一次 —— 上面那条新待办还在 = 成功
```