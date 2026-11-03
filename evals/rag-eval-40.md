# RAG 评估集 40 题 · v0.3

> 2026-11-03 · 条件 ③（RAG）· deepseek-chat · temperature=0
> 数据：`rag-eval-40-baseline.jsonl`（40 行）· 判分：`judge-40.jsonl` / `judge-40.md`

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

**holdout 规则**：Q31–Q40 只在里程碑（版本冻结、面试前）跑，平时调参只看 train。

## 3. 怎么跑

```powershell
# 1) 生成答案（条件 ③ RAG）
.\.venv\Scripts\python.exe evals\run_baseline.py --eval evals\rag-eval-40.jsonl --conditions rag `
    --out evals\rag-eval-40-baseline.jsonl

# 2) LLM 判分（自动带 gold_sources + 检索到的文件全文作对照）
.\.venv\Scripts\python.exe evals\judge.py --answers evals\rag-eval-40-baseline.jsonl `
    --out evals\judge-40.jsonl
```

`judge.py` 的 key 先读 `DEEPSEEK_API_KEY`，再退到 Windows 凭据；`--no-context` 可关掉语料对照（不建议）。

## 4. 结果（2026-11-03）

| 口径 | 值 |
|---|---|
| 要点命中 | **117 / 170 = 68.8%** |
| train（30 题） | 90 / 130 = 69.2% |
| holdout（10 题） | 27 / 40 = 67.5% |
| 幻觉题 | 2 / 40 = 5%（Q7、Q18） |
| Q1–Q10 子集 | 79.1%（旧 10 题集人工口径 8.56/10） |

按难度：1 档 79.3% · 2 档 65.8% · 3 档 69.6% · 4 档 55.6%。按题型：事实题 73%、代码推理 60%、跨文件 67%、拒答 64%。

**这不是回归。** 旧 8.56/10 是 commit `dad0e13` 上 10 道事实题的分数；新集里 22 道是跨文件/机制/陷阱题，且 Q1–Q10 子集在本次跑分仍是 79.1%。holdout 与 train 只差 1.7 个点，说明题目不是照着实现写的。

### 主要失分点（人工复核后）

| 题 | 得分 | 原因 |
|---|---|---|
| Q3 | 0 / 4 | 问 FastAPI 启动种子数据，检索只给了 main.py 结构概览，模型答「资料中没有」——检索没召回 `store.py` 的 `_seed()` |
| Q21 | 0 / 4 | 问 `/rag` 与 `/chat` 的 temperature 取舍；`/chat` 函数体没被召回，模型据实拒答。**题目本身偏推断，待复核** |
| Q25 | 0 / 3 | 问 `sort` / `sorted` / `[:]`；旧要点里混了 `del` / `remove`（与题干无关），已修订为 3 个要点 |
| Q39 | 0 / 4 | 问测试与 CI；`package.json` 没被召回，模型答「资料中没有」。**属于检索失败，不是答错** |
| Q17 | 1 / 5 | 长链路机制题（tool 消息顺序），只答对开头 |

## 5. 判分器校准

拿 `baseline-dad0e13-20261018-rag.jsonl`（10 条人工逐题打分）对照：

| 指标 | 结果 |
|---|---|
| 要点完全一致 | **8 / 10** |
| 平均绝对误差 | 0.2 分/题 |
| 幻觉判定一致 | 10 / 10 |

已知偏差：Q6 判宽 1 分（兜底分支没答也算命中），Q7 判严 1 分（模型诚实说「资料未展示」被记为未命中）。**结论：judge 可用于看趋势和批量回归，不能替代里程碑前的人工抽检（20%，holdout 全查）。**

## 6. 待办

1. Q21 改写或降级为「推断题」，避免把「据实拒答」判成 0。
2. Q39 保留为检索失败样例，但在报告里单列，不与知识题混算。
3. 下一步跑三条件对比（noctx / fullctx / rag）到 40 题，给出「有资料值多少分」的新数字。
4. 把 `judge.py` 接进 CI 的离线任务（只跑 train、限 10 题、失败即红）。
