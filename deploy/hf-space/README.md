---
title: Todo + Agent + RAG
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Todo + Agent + RAG

FastAPI 待办服务：SQLite、SSE 流式对话、Function Calling、手写 ReAct、本地 RAG（Chroma + 混合检索 + 查询改写）、MCP 工具化、可观测面板。

- 演示页：`/app/`（React）
- API 文档：`/docs`
- 静态演示：`/rag-ui`
- 用量面板：`/stats-ui`

源码：<https://github.com/Aozak1Aok0/todo-rag>

> 需要在 Space 的 Settings → Variables and secrets 里配置 `DEEPSEEK_API_KEY`。