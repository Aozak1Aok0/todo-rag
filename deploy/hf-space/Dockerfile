# Hugging Face Spaces (Docker) — 构建时从 GitHub 拉取项目，并构建 React 前端
# Space 里只需要放这个 Dockerfile 和 README.md（带 frontmatter）

# ---- 1) 构建前端 ----
FROM node:20-slim AS web
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 https://github.com/Aozak1Aok0/todo-rag.git .
WORKDIR /src/web
RUN npm ci && npm run build

# ---- 2) 运行后端 ----
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone --depth 1 https://github.com/Aozak1Aok0/todo-rag.git .

# 前端构建产物（web/dist 在 .gitignore 里，所以从 web 阶段拷过来）
COPY --from=web /src/web/dist ./web/dist

# 依赖（chromadb / fastembed / mcp 都在 requirements 里）
RUN python -m pip install -r requirements.txt

# 本地 embedding 模型（约 91MB，不进仓库）
RUN mkdir -p models/bge-small-zh-v1.5 \
 && cd models/bge-small-zh-v1.5 \
 && for f in config.json model_optimized.onnx special_tokens_map.json tokenizer.json tokenizer_config.json vocab.txt; do \
      curl -sL --fail "https://huggingface.co/Qdrant/bge-small-zh-v1.5/resolve/main/$f" -o "$f"; \
    done

# 构建检索索引（63 块，约 10s）
RUN python rag/rag.py build

# Spaces 以非 root 用户运行：放开写权限（todos.db / logs / chroma 查询）
RUN chmod -R a+rwX /app

EXPOSE 7860

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]