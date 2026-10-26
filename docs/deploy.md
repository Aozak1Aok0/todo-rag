# 部署：Hugging Face Spaces（Docker，免费）

> 本机没有 Docker，**镜像未在本地构建过**；下面的步骤按 HF Spaces 的 Docker SDK 写成，第一次部署时按日志排错。

## 0. 前置

1. 先把最新改动 push 到 GitHub（镜像构建时会 `git clone` 公开仓库）：
   ```powershell
   cd D:\Experienment.py\todo-rag
   git push origin main
   ```
2. 注册/登录 <https://huggingface.co>（免费）。

## 1. 创建 Space

- 打开 <https://huggingface.co/new-space>
- Name：`todo-rag`
- License：MIT（可选）
- **SDK：Docker** → Hardware：**CPU basic · 2 vCPU · 16GB RAM · Free**
- Visibility：Public
- 点 **Create Space**

## 2. 配置 key（Secret）

Space 页面 → **Settings** → **Variables and secrets** → **New secret**：

- Name：`DEEPSEEK_API_KEY`
- Value：你的 DeepSeek key

（应用优先读环境变量，读不到才尝试 Windows 凭据管理器 —— 在 Linux 上会直接失败，所以这个 Secret 是必需的。）

## 3. 上传两个文件

Space 页面 → **Files** → **Add file** → **Upload files**，上传：

- `deploy/hf-space/Dockerfile`
- `deploy/hf-space/README.md`（带 HF frontmatter，**不要**用项目根目录那个 README）

> 也可以 `git clone https://huggingface.co/spaces/<你的用户名>/todo-rag` 后把这两个文件拷进去再 push。

## 4. 等构建

- 页面 **Logs** 会显示：pip 安装 → 下载模型（91MB）→ `rag.py build`（63 块）→ uvicorn 启动
- 首次构建约 **5–10 分钟**；之后冷启动约 30 秒

## 5. 验收

打开：

- `https://<用户名>-todo-rag.hf.space/app/` —— React 前端
- `https://<用户名>-todo-rag.hf.space/docs` —— API 文档
- `https://<用户名>-todo-rag.hf.space/rag-ui` —— 静态演示页
- `https://<用户名>-todo-rag.hf.space/stats-ui` —— 用量面板

问一句「这个服务启动时 todos 里有哪些数据？」，能看到答案 + 引用 + 校验条即为成功。

## 常见问题

| 现象 | 处理 |
|---|---|
| Build 失败在 `pip install` | 换 `requirements.txt` 里的版本或看 Logs 定位到具体包 |
| Build 失败在下载模型 | 检查 `huggingface.co` 链接是否可访问；可改为 `hf-mirror.com` |
| 启动后 500「未找到 DeepSeek API key」 | Secret 没配或名字拼错（必须 `DEEPSEEK_API_KEY`） |
| `/app/` 404 | Dockerfile 用多阶段构建（`node:20-slim` 里 `npm ci && npm run build`），确认这一步没报错 |
| 内存不足 | 免费层 16GB，一般不会；若发生，减小 `RAG_K` 或去掉 fastembed |

> `web/dist/` 不进仓库：Dockerfile 用 **多阶段构建**（`node:20-slim` 里 `npm ci && npm run build`），
> 再把 `dist` 拷进运行镜像，所以不需要改 `.gitignore`。