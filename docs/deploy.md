# 部署与演示（2026-10-27）

**在线地址：<https://aozak1aok0.github.io/todo-rag/>**（已可访问；静态回放，不调用模型）

## 0. 结论

- 静态演示（真实运行回放）**优先托管在 GitHub Pages**：免费、无需额外账号、更新简单。
- Hugging Face 的 Static Space 也可以，但需要确认可见性是 Public；Docker / Gradio 在当前账号下收费，不采用。
- 完整交互（真检索 + 真生成）在本地跑，命令见第 3 节。
- `gh-pages` 分支**只应包含** `index.html`、`data.json`、`screenshot.png`、`.nojekyll`；
  不要发布 `todos.db`、`logs/`、`models/`、`web/node_modules/` 等运行时文件。

## 1. GitHub Pages（推荐）

静态文件在 `deploy/hf-static/`：`index.html`、`data.json`、`screenshot.png`。

### 一次性发布

1. 先把当前改动提交到 `main` 并推送（工作区必须干净）；
2. 运行发布脚本（会把静态文件推到一个独立的 `gh-pages` 分支；远端已存在时加 `-Force`）：

```powershell
cd D:\Experienment.py\todo-rag
powershell -NoProfile -ExecutionPolicy Bypass -File deploy\gh-pages\publish.ps1 -Force
```

3. 打开仓库 **Settings → Pages**：
   - Source：**Deploy from a branch**
   - Branch：**gh-pages** / **/ (root)**
   - Save
4. 等 1–2 分钟，访问：

```
https://aozak1aok0.github.io/todo-rag/
```

发布后自检（应只列出 4 个文件）：

```powershell
git fetch origin gh-pages
git ls-tree --name-only origin/gh-pages
# 期望：.nojekyll  data.json  index.html  screenshot.png
curl.exe -sS -o NUL -w "%{http_code}`n" https://aozak1aok0.github.io/todo-rag/
```

### 以后更新回放数据

```powershell
.\.venv\Scripts\python.exe evals\verify_eval.py --revisions 0 --multi-query --k 10 --out evals\verify-multi-k10-20261026.jsonl
.\.venv\Scripts\python.exe deploy\hf-static\build_data.py
git add deploy/hf-static/data.json && git commit -m "docs: refresh demo data" && git push
powershell -NoProfile -ExecutionPolicy Bypass -File deploy\gh-pages\publish.ps1 -Force
```

> 脚本每次会重建 `gh-pages` 分支；远端已存在时加 `-Force` 覆盖（历史每次都会被重写，对生成内容是可接受的）。

## 2. Hugging Face Static Space（备选）

文件同上。步骤：

1. <https://huggingface.co/new-space> → Name `todo-rag-demo` → **SDK：Static** → Public；
2. Files → Upload files：`index.html`、`data.json`、`screenshot.png`、`README.md`（HF 版 frontmatter）；
3. 等 Running，访问 `https://<用户名>-todo-rag-demo.hf.space`。

排错：直连域名 404 = Space 未 Running / 私有 / 文件在子目录；用无痕窗口确认可见性。

## 3. 本地完整交互（面试演示用）

```powershell
cd D:\Experienment.py\todo-rag
.\.venv\Scripts\python.exe -m uvicorn main:app --port 8000

# 另一个终端
cd web
npm run dev        # http://127.0.0.1:5173
```

或构建后直接开 <http://127.0.0.1:8000/app/>。

## 4. Docker Space（备选，账号支持免费 Docker 时）

`deploy/hf-space/` 保留了一套多阶段 Dockerfile（Node 构建前端 + Python 运行 + 下载模型 + 建索引）。
上传 `Dockerfile` 与 `README.md`，配置 Secret `DEEPSEEK_API_KEY`，端口 7860。**本机无 Docker，未验证。**
