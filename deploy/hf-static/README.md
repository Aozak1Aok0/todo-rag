---
title: Todo + Agent + RAG · 演示回放
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: static
pinned: false
---

# Todo + Agent + RAG · 演示回放

这是 **静态回放**：页面展示 10 道评测题的真实运行结果（答案、引用、校验），不调用模型，也不需要后端。

- 完整交互（提问 → 混合检索 → 生成 → 校验）需在本地运行：见 GitHub 仓库 README
- 源码：<https://github.com/Aozak1Aok0/todo-rag>

## 数据说明

- 运行时间：2026-10-26
- 模型：DeepSeek `deepseek-chat`；检索：Chroma + BM25 混合 + 查询改写（k=10）
- 校验：独立校验 Agent，**只报告不改写**（自动重写的实测分数更低，详见仓库 `docs/dual-agent.md`）