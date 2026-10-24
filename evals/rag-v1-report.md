# RAG v1 报告（2026-10-20 · Chroma 接入）

> 代码：`rag/rag.py` + `rag/lexical.py` + `evals/retrieval_eval.py`；索引：`chroma_db/`（46 块）
> 条件② 对照：`baseline-dad0e13-20261018.jsonl`（fullctx 9.42 / 7,195 token/题）
> 条件③：`baseline-dad0e13-20261018-rag.jsonl`（k=5）、`…-rag-k8.jsonl`（k=8）

## 1. 链路

```
corpus.txt(15 文件) → 按行切块(30 行/8 行重叠) → bge-small-zh 向量化 → Chroma(pra_corpus)
                                                          ↘ 代码文件额外生成「结构概览」块
问题 → 向量 top-20 + BM25 top-20 → RRF 融合 → 两条覆盖规则 → 取 top-k → 拼 prompt → deepseek-chat
```

两处关键设计：
- **混合检索（向量 + BM25）**：纯向量在 Q5（requirements.txt）/Q8（note/JS.txt）上直接 MISS —— bge-small-zh 对代码标识符和文件名区分度不足；BM25 补字面匹配，RRF 融合不用调权重。
- **文件路径写进块文本 + 代码文件生成结构概览块**：点名文件的查询能召回；「有哪些路由」这类题有一张现成的清单可看。

## 2. 检索指标（10 题，文件级）

| 配置 | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|
| 纯向量 k=5 | 7/10 | 8/10 | 8/10 | 0.750 |
| 混合 k=5 | 7/10 | **10/10** | **10/10** | 0.850 |
| 混合 k=8 | — | 10/10 | 10/10 | — |

> 命中按「文件去重后的名次」算（gold 是文件级标注）。Q5/Q8 是纯向量的两个硬伤，混合后修复。

## 3. 生成结果（同一套 10 题）

| 条件 | 分数 | 幻觉 | 平均输入 token | 相对 fullctx |
|---|---|---|---|---|
| ① noctx | 1.00 / 10 | 4 题 | 42 | — |
| ② fullctx | 9.42 / 10 | 0 | 7,195 | 基准 |
| ③ RAG k=5 | **7.75 / 10** | 0 | **1,340（-81%）** | -1.67 |
| ③ RAG k=8 | **8.3–8.6 / 10**（两次运行：8.33 / 8.56） | 0 | 2,171（-70%） | ≈ -0.9 |

## 4. 差距在哪（k=5 → k=8）

| 题 | k=5 | k=8 | 原因 |
|---|---|---|---|
| Q1 路由清单 | 6/9 | 8/9 | 5 块只覆盖 main.py 前 160 行；k=8 才看到 `/agent-raw`。仍缺 `/agent` |
| Q7 Express vs FastAPI | 1/4 | 2/4 | 5 块里 FastAPI 侧只有 CRUD 片段，没拿到 `init_db()` 的 DDL；k=8 覆盖到"连接式操作"，但表结构仍未完整出现 |
| Q8 语料纠错 | 1/3 | 2/3 | **"仅根据资料"把世界知识压住了**：资料没写"这是笔误"，模型就不敢断言（k=8 补上了 startsWith，但仍未点明笔误） |
| Q9 缺字段检查 | 3/4 | 3/4 | 少一个加分点（多用户该怎么改），不是检索问题 |
| 其余 | 满分 | 满分 | |

## 5. 四条结论

1. **RAG 的价值成立**：1,340 token 换 7.75 分（fullctx 要 7,195 token 换 9.42）。k=8 是 2,171 token 换 8.56 —— 每加 800 token 约换回 0.8 分。
2. **瓶颈不是模型，是「覆盖」**：Q1/Q7 丢分都因为 top-k 没覆盖到关键块。下一步优先级最高的是**按符号切块**（每个 `@app.*` + 函数体一块，并带符号名），而不是继续加 k。
3. **过度 grounding 会伤「纠错」类问题**：Q8 在 fullctx 下 2/3、RAG 下 1~2/3。提示词可以加一句「资料可能包含笔误；若与公认事实冲突，请指出」，但要小心别把幻觉放回来 —— 值得单独做一组 A/B。
4. **k 是超参，不是越大越好**：k=5→8 涨 0.81 分，但 token 涨 62%。要不要接受，取决于你的成本目标（当前 DeepSeek 价格下差异很小，教学项目建议先取 k=8）。

## 6. 复现

```powershell
cd <repo>
.\.venv\Scripts\python.exe rag\rag.py build
.\.venv\Scripts\python.exe evals\retrieval_eval.py            # 检索层，秒级、不花钱
$env:RAG_K="8"
.\.venv\Scripts\python.exe evals\run_baseline.py --conditions rag
```

## 7. 下一步（按性价比）

1. **按符号切块**（code-aware chunking）：`@app.get/post/...` + 函数体为一块，块头写 `# 端点: GET /api/todos`；预计 Q1/Q7 直接补齐。
2. **Q8 的提示词 A/B**：加不加「可指出资料中的笔误」，各跑 3 次看幻觉是否回来。
3. **接进 FastAPI**：`POST /rag`（检索 + 回答 + 返回 sources），前端可直接使用。
4. 条件③ 用 **N=3 取平均**，把噪声压下去再下结论（单次 run 的 ±0.3 不可信）。

## 8. 实验：按符号切块（`CHUNK_MODE=symbol`）—— 结论是「先别用」

想解决 Q1/Q7 的覆盖问题，试过把代码文件按 `@app.xxx + 函数体` 切成语义块（71 块，块头带「端点 GET /api/todos」「函数 init_db」）。**检索指标反而退化了**：

| 配置 | 块数 | hit@1 | hit@3 | MRR |
|---|---|---|---|---|
| window（默认，30 行/8 重叠） | 46 | **7/10** | 10/10 | **0.850** |
| symbol（按符号切） | 71 | 5/10 | 10/10 | 0.750 |

典型症状：Q7 的 top-10 里 9 条来自 `server.js`，`main.py` 只挤进一条 `ChatRequest` —— 而 `init_db`、`DELETE` 等关键块都排在 10 名以外。Q1 的 `main.py` 结构概览也进不了 top-5。

原因（判断，不是断言）：
1. **bge-small-zh 是小体量中文模型**，对英文标识符/代码符号的语义区分度弱；块越短，越依赖 header 文本，而 header 又高度同质（都是「# 文件：xxx · 端点 GET ...」）。
2. 窗口块带上下文（注释 + 前后代码），反而给了模型更多可用信号。

所以：**代码已保留，但默认切回 window**（`CHUNK_MODE` 环境变量可切）。没有继续花条件③的调用费 —— 检索层已经退化，生成层没有测的价值。

下一步建议：换更强的多语/代码 embedding（bge-m3 之类，体积约 2GB）后再重试符号切块；否则就在 window 块上做「覆盖类」优化（比如 k=8 + 对点名文件强制补一块）。

## 9. 已接进 FastAPI：`POST /rag`

```jsonc
// 请求
{"question": "这个服务为什么要把 Swagger 资源放本地？", "k": 5}

// 响应
{"answer": "...", "k": 5,
 "sources": [{"source": "python/fastapi-api/main.py", "start_line": 23, "end_line": 52, "distance": 0.49}, ...],
 "usage": {"in": 1361, "out": 126}}
```

实现要点（`main.py` 末尾）：
- **懒加载** `rag.rag` / `rag.prompt`：没建索引、没装依赖时，基础接口照常可用；检索失败返回 **503**，模型失败返回 **502**。
- `retrieve()` 是同步的（embedding + chroma），用 `run_in_threadpool` 丢到线程池，避免卡事件循环。
- `k` 默认走环境变量 `RAG_K`（默认 8）；`k=0` 这种要用 `is None` 判断，不能用 `or`（0 会被当成没传）。
- 返回 `sources` 带文件名 + 行号 + 距离，前端可以直接展示"答案引用自哪几行"。
- 提示词与评测共用 `rag/prompt.py`，保证"评测口径 = 线上口径"。

实测（TestClient，一次真实调用）：200，answer 正常，sources 5 条，usage in=1361/out=126；空问题 / k 越界 → 400。

## 10. 已知问题（下次升 eval v0.3 时处理）

`app.routes` 实际还注册了 **`/openapi.json`** 和 **`/redoc`**（FastAPI 默认；`docs_url=None` 只关掉了默认 `/docs`）。而 Q1 的 gold 只有 9 条、没算这两个 —— 也就是说，
回答里提到 `/redoc` 不会被扣分（我们不罚"多答"），但**也没被计入得分**。要更严谨，就把 Q1 的锚点补到 11 条，并重判历史 Q1（v1/v2/rag 都只需改这一题）。

## 11. 演示页 `/rag-ui`

`static/rag.html`（单文件、零外部依赖，符合本项目"不靠 CDN"的约定）+ 路由 `GET /rag-ui`：

- 输入框 + 快捷问题 chips + `k` 选择（3/5/8/10）；
- 回答按纯文本渲染（`textContent`，不拼 HTML，避免模型输出注入）；
- 引用区展示 `文件 · 行号范围 · 余弦距离 · 片段预览`（`/rag` 响应新增 `preview` 字段，取块正文前 160 字）；
- 显示耗时与 token 用量，方便当场看成本；
- 根路径 `/` 现在返回 `{"ui": "/rag-ui", "docs": "/docs", ...}`，便于发现。

启动后打开 <http://127.0.0.1:8000/rag-ui>。