# RAG 评估集 40 题 · v0.3

> 2026-11-04 · deepseek-chat · temperature=0
> 数据：`rag-eval-40-baseline.jsonl`（条件 ③）、`rag-eval-40-3cond.jsonl`（三条件，120 行）
> 判分：`judge-40.jsonl` / `judge-40.md`、`judge-3cond.jsonl` / `judge-3cond.md`

## 1. 为什么从 10 题扩到 40

10 题集上 hit@3 已经是 10/10、RAG 得分 8.56/10，指标饱和，任何检索改动都测不出差别（详见 `docs/rerank.md`）。扩题的目的不是把分数做低，而是让**改动有区分度**：加入跨文件题、机制题、语料陷阱题和 4 道应当拒答的题。

## 2. 数据集

| 项 | 值 |
|---|---|
| 题数 | 40（Q1–Q40） |
| 划分 | train 30（Q1–Q30）· holdout 10（Q31–Q40） |
| 难度 1/2/3/4 | 6 / 18 / 14 / 2 |
| 应拒答（must_refuse） | 4 |
| 复用 | Q1–Q10 来自 `rag-eval-10.jsonl`（v0.2），补 `split=train` |
| 新写 | Q11–Q40（v0.3）：跨文件对比、机制解释、语料纠错、无鉴权/无测试等应拒答题 |

字段：`id / type / difficulty / split / question / expected_points / gold_sources / must_refuse / notes / eval_version`。`gold_sources` 带 `pra/` 前缀，判分器会自动去掉再读 `corpus/`。

**holdout 规则**：Q31–Q40 只在里程碑（版本冻结前）跑，平时调参只看 train。

## 3. 怎么跑

```powershell
# 1) 三条件一起跑（noctx / fullctx / rag）
.\\.venv\\Scripts\\python.exe evals\\run_baseline.py --eval evals\\rag-eval-40.jsonl `
    --conditions noctx,fullctx,rag --out evals\\rag-eval-40-3cond.jsonl

# 2) LLM 判分（自动带 gold_sources + 检索到的文件全文作对照）
.\\.venv\\Scripts\\python.exe evals\\judge.py --answers evals\\rag-eval-40-3cond.jsonl `
    --out evals\\judge-3cond.jsonl
```

`judge.py` 的 key 先读 `DEEPSEEK_API_KEY`，再退到 Windows 凭据；`--no-context` 可关掉语料对照（不建议）。
`run_baseline.py` 的语料根是 `corpus/`（manifest `evals/corpus.txt` 的路径相对于它）。

## 4. 结果（40 题，2026-11-04）

| 条件 | 要点命中 | train | holdout | 幻觉题 | 平均输入 token |
|---|---|---|---|---|---|
| ① noctx（无资料） | 81 / 169 = **47.9%** | 48.1% | 47.5% | 19 / 40 | 41 |
| ② fullctx（全语料 31.5K 字符） | 151 / 169 = **89.3%** | 89.9% | 87.5% | 0 / 40 | 9,692 |
| ③ RAG（检索 top-k） | 126 / 169 = **74.6%** | 75.2% | 72.5% | 1 / 40 | 1,470 |

- **有资料 vs 没资料**：fullctx 比 noctx 高 41.4 个点，幻觉从 19 题降到 0。
- **RAG 用 15% 的 token 拿到 fullctx 84% 的分数**（1470 vs 9692），代价是 14.7 个点和 1 题幻觉。
- Q1–Q10 子集：noctx 37.2% / fullctx 95.3% / rag 79.1%，与旧 10 题集的人工口径（1.00 / 9.42 / 8.56）方向一致。
- holdout 与 train 差 1–3 个点，说明题目不是照着实现写的。

**口径警告（noctx）**：47.9% 是上限，不是「无资料也能答对一半」。判分器会把「猜中通用行为」的答案算命中——旧 10 题集人工口径下 noctx 只有 1.00/10，而同一批题在本判分器下是 37.2%。引用 noctx 时务必带上这句。

### 主要失分点（RAG 条件，人工复核过）

| 题 | 得分 | 原因 |
|---|---|---|
| Q3 | 0 / 4 | 问 FastAPI 启动种子数据，检索只给了 main.py 结构概览，没召回 `store.py`，模型答「资料中没有」 |
| Q17 | 1 / 5 | 两边 DELETE 差异题，模型错误声称响应内容缺失，并编造了一条不存在的差异（本集唯一幻觉） |
| Q24 | 1 / 5 | `points.essential` 的 `*args` / `del` / `pop` 机制只答对元组打包 |
| Q32 | 1 / 3 | `/rag` 的 `k` 默认值与范围没说对，反而断言资料未给出 |
| Q18 | 2 / 5 | `express.json()` 的作用答对，但 PATCH 的三条校验全部没答 |

Q3、Q17、Q18、Q39 的共同点：**答案本身没错，是检索没把关键文件召回**。这比「模型答错」更值得修，也是后面 rerank / 混合检索要解决的问题。

## 5. 判分器校准

拿 `baseline-dad0e13-20261018-rag.jsonl`（10 条人工逐题打分）对照：

| 指标 | 结果 |
|---|---|
| 要点完全一致 | **8 / 10** |
| 平均绝对误差 | 0.2 分/题 |
| 幻觉判定一致 | 10 / 10 |

另抽 8 题（Q2/Q7/Q13/Q18/Q22/Q27/Q33/Q39）人工复核：6/8 完全一致，2 题 judge 偏宽（Q7 +1、Q13 +2），平均 +0.4 分/题。

已知偏差：
- 对「猜中通用行为」偏宽（noctx 被高估，见上）。
- 对「诚实说资料没有」判严（该要点记未命中，符合「说出来了没有」的口径，但会让拒答题显得低分）。
- 长答案截断到 512 token 后，机制题的多步要点容易漏判。

**结论：judge 可用于看趋势和批量回归，不能替代里程碑前的人工抽检（20%，holdout 全查）。**

## 6. 待办

1. CI 接入离线判分任务（只跑 train、限 10 题、失败即红）。
2. 补 4 道 must_refuse 题的人工复核（当前 3/4 命中拒答口径）。
3. 修 Q3 / Q18 / Q39 的检索召回（`store.py`、`server.js` 的 PATCH 段、`package.json`）。
4. 用本集重跑 `docs/rerank.md` 的结论：10 题饱和是 rerank 无效的原因之一，40 题集上值得再试一次。
