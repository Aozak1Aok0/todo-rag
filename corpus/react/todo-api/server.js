const express = require("express");
const cors = require("cors");
const { DatabaseSync } = require("node:sqlite");

const app = express();
// 生产环境只允许前端域名访问；本地没设 FRONTEND_URL 时退化为 "*"（开发方便）
app.use(cors({ origin: process.env.FRONTEND_URL || "*" }));
app.use(express.json()); // 关键：解析 POST 请求体，req.body 才有值

// 打开（没有就新建）一个文件数据库，数据持久保存，重启不丢
const db = new DatabaseSync("todos.db");

// 建表（已存在就跳过）
db.exec(`
  CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    completed INTEGER DEFAULT 0
  )
`);

// 表是空的就塞三条默认数据，列表不至于空白
const { count } = db.prepare("SELECT COUNT(*) AS count FROM todos").get();
if (count === 0) {
  const seed = db.prepare("INSERT INTO todos (name, completed) VALUES (?, ?)");
  seed.run("学 Express", 1);
  seed.run("接前端", 0);
  seed.run("学 SQLite", 0);
}

// GET：列出全部。SQLite 里 completed 是 0/1，转成布尔值再给前端
app.get("/api/todos", (req, res) => {
  const rows = db.prepare("SELECT * FROM todos").all();
  const todos = rows.map((r) => ({ ...r, completed: r.completed === 1 }));
  res.json(todos);
});

// POST：新增一条
app.post("/api/todos", (req, res) => {
  const name = (req.body?.name || "").trim();
  if (!name) {
    return res.status(400).json({ error: "name 不能为空" }); // 400 = 请求有误
  }
  const result = db
    .prepare("INSERT INTO todos (name, completed) VALUES (?, 0)")
    .run(name);
  res.status(201).json({ id: Number(result.lastInsertRowid), name, completed: false }); // 201 = 已创建
});
// DELETE：删除一条
app.delete("/api/todos/:id", (req, res) => {
  const id = Number(req.params.id); // URL 里的 :id 是字符串，转成数字
  const result = db.prepare("DELETE FROM todos WHERE id = ?").run(id);
  if (result.changes === 0) {
    return res.status(404).json({ error: "找不到这条待办" }); // 404 = 不存在
  }
  res.status(204).end(); // 204 = 成功但无内容，删除常用
});

// PATCH：切换完成状态
app.patch("/api/todos/:id", (req, res) => {
  const id = Number(req.params.id);
  const { completed } = req.body;
  if (typeof completed !== "boolean") {
    return res.status(400).json({ error: "completed 必须是布尔值" });
  }
  const result = db
    .prepare("UPDATE todos SET completed = ? WHERE id = ?")
    .run(completed ? 1 : 0, id);
  if (result.changes === 0) {
    return res.status(404).json({ error: "找不到这条待办" });
  }
  const updated = db.prepare("SELECT * FROM todos WHERE id = ?").get(id);
  res.json({ ...updated, completed: updated.completed === 1 });
});

app.get("/", (req, res) => {
  res.send("Todo API 运行中");
});

app.listen(3000, () => {
  console.log("服务已启动：http://localhost:3000");
});
