# Rerank：bge-reranker-base 的 A/B（2026-11-03）

> 代码：`evals/rerank_eval.py` · 模型：`BAAI/bge-reranker-base`（fastembed `TextCrossEncoder`）
> 结果：`evals/rerank-20261103-1957.{jsonl,md,manifest.json}`
> 结论：**不上线**。文件级指标零变化，块级 +0.033，代价是每题 +4.3 秒。

## 1. 设计

两个变体，共享同一个候选池，只改排序：

```
问题
  │
  ├─▶ base：生产 retrieve(q, pool=20) 的返回顺序
  │         （含「点名文件置顶」+「列表类附带结构概览」两条规则）
  │
  └─▶ rerank：同一批 20 个候选，cross-encoder 逐条 (query, chunk) 打分 → 稳定排序
              （纯排序，不重新应用任何规则）
```

为什么固定池子：把**召回**和**排序**分开。池子一样，指标差异就只来自排序器。
为什么 rerank 不还原规则：先测排序器本身的贡献；规则和模型打架是后面单独要回答的问题。

指标同时看文件级与块级：rerank 的主要作用是在**同一文件内部**重排，文件级去重后会被掩盖。

| 层级 | 指标 |
|---|---|
| 文件级（去重，gold 命中即算） | hit@1 / hit@3 / hit@5、MRR、nDCG@5 |
| 块级 | chunk@1 / chunk@3、chunk_mrr |
| 性能 | retrieve 与 rerank 的 P50 / P95 |

## 2. 基线校验

`--no-rerank` 只跑 base，必须与 `evals/retrieval_eval.py` 的数字一致，否则说明候选池或去重口径有差异：

| 指标 | retrieval_eval | rerank_eval --no-rerank |
|---|---|---|
| hit@1 | 7/10 | 7/10 |
| hit@3 | 10/10 | 10/10 |
| MRR | 0.850 | 0.850 |
| nDCG@5 | 0.899 | 0.899 |
| chunk_mrr | 0.817 | 0.817 |

一致。基线可信，后面的对比才有意义。

## 3. 实测（10 题，池 20，top-5）

| 指标 | base | rerank | Δ |
|---|---|---|---|
| hit@1 | 7/10 | 7/10 | 0 |
| hit@3 | 10/10 | 10/10 | 0 |
| hit@5 | 10/10 | 10/10 | 0 |
| MRR | 0.850 | 0.850 | 0 |
| nDCG@5 | 0.899 | 0.892 | -0.007 |
| chunk_mrr | 0.817 | 0.850 | **+0.033** |
| 延迟 P50 | 17 ms | **4,324 ms** | +4.3 s |
| 延迟 P95 | 328 ms | 4,545 ms | +4.2 s |

逐题只有两处变化，一正一负：

| 题 | base 名次 | rerank 名次 | 说明 |
|---|---|---|---|
| Q4 | 2 | **1** | 真收益：`main.py` 排到 `server.js` 前，语义相关性压过词汇匹配 |
| Q5 | 1 | 2 | 负收益：`requirements.txt` 的「点名置顶」被冲掉，`JS.txt` 因正文提到 requirements.txt 被顶到第一 |

## 4. 为什么是平局

**① 指标饱和。** hit@3 已经 10/10、hit@5 也 10/10，排序器没有任何提升空间。这不是 rerank 不行，
是这套题没有区分度——同样的道理，`docs/dual-agent.md` 里多查询在文件级也测不出差别。

**② 规则与模型冲突。** 生产链路里有两条确定性规则（点名文件置顶、列表类附结构概览），
纯 rerank 会把它们覆盖掉。Q5 就是代价：一条 100% 准确的规则，输给了概率模型的判断。

**③ 长块被截断。** 块最长 1,500 字符，而 xlm-roberta 上限 512 token（中文近似 1 字符 1 token），
后 2/3 根本没进模型。关键词落在块尾时，rerank 天生看不见。

**④ 推理成本。** fp32 CPU 上 1.1GB 模型跑 20 个候选要 4.3 秒，而检索本身只要 17 ms。
即使文件级有 +5% 的收益，这个延迟在生产里也不可接受。

## 5. 结论

1. **不接入生产**，`retrieve()` 保持现状；
2. 如果还要试，按性价比排序：
   - int8 量化（延迟可能降到 1/3）或池缩到 10；
   - 只喂块的前 512 字符（消除截断，但会丢块尾信息，需对比）；
   - rerank 后**重新应用**点名置顶规则（保留确定性收益）；
3. 真正的瓶颈是**评测集区分度**：10 题 hit@3=100%，任何排序改动都会是平局。要验证排序器，
   先扩到 40 题（含 10 题 holdout），再谈 A/B。

## 6. 复现

```powershell
# 模型不在仓库里（1.1GB，models/* 已 gitignore），先下载到 models/bge-reranker-base/
# 需要 config.json、tokenizer.json、tokenizer_config.json、special_tokens_map.json、onnx/model.onnx
.\\.venv\\Scripts\\python.exe evals\\rerank_eval.py --no-rerank   # 只跑基线
.\\.venv\\Scripts\\python.exe evals\\rerank_eval.py --pool 20 --k 5
```

脚本在模型缺失时会打印 hf-mirror 的下载地址并以 exit 2 退出；结果前缀默认带时间戳，
全部产物的 sha256 记录在 `.manifest.json` 里。
