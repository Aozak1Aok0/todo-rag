# rerank 评测 20261104-1333

- 池：20 · top-5 · 题数：40 · 模型：`BAAI/bge-reranker-base`
- 变体：base（生产顺序）vs rerank（纯排序，不还原点名文件的置顶规则）

| 指标 | base | rerank | Δ |
|---|---|---|---|
| hit@1 | 34 | 34 | +0.000 |
| hit@3 | 39 | 39 | +0.000 |
| hit@5 | 39 | 39 | +0.000 |
| mrr | 0.912 | 0.912 | +0.000 |
| ndcg@5 | 0.933 | 0.929 | -0.004 |
| chunk@1 | 34 | 34 | +0.000 |
| chunk@3 | 39 | 39 | +0.000 |
| chunk_mrr | 0.904 | 0.912 | +0.008 |

延迟：retrieve p50/p95 = 96/220 ms；rerank p50/p95 = 10163/12695 ms

## 逐题

| 题 | base 名次 | rerank 名次 | base top5 | rerank top5 |
|---|---|---|---|---|
| Q1 | 1 | 1 | main.py, store.py, server.js, requirements.txt | main.py, requirements.txt, store.py, server.js |
| Q2 | 1 | 1 | main.py, server.js, Css.html | main.py, Css.html, server.js |
| Q3 | 2 | 2 | server.js, main.py, store.py | server.js, store.py, main.py |
| Q4 | 2 | 1 | server.js, main.py, points.essential.txt, store.py | main.py, server.js, store.py, points.essential.txt |
| Q5 | 1 | 2 | requirements.txt, verse4.txt, verse2.txt, points.essential.txt, main.py | JS.txt, requirements.txt, points.essential.txt, verse1.txt, verse2.txt |
| Q6 | 1 | 1 | main.py, store.py, points.essential.txt, JS.txt, server.js | main.py, JS.txt, server.js, store.py, points.essential.txt |
| Q7 | 1 | 1 | main.py, server.js, package.json, store.py, index.js | server.js, package.json, main.py, store.py, index.js |
| Q8 | 1 | 1 | JS.txt, verse4.txt, verse2.txt, verse3.txt, main.py | JS.txt, package.json, server.js, main.py, requirements.txt |
| Q9 | 2 | 2 | server.js, main.py, store.py, hellonode.js, index.js | server.js, store.py, main.py, index.js, hellonode.js |
| Q10 | 1 | 1 | main.py, store.py, server.js | main.py, store.py, server.js |
| Q11 | 1 | 1 | main.py, points.essential.txt, server.js, store.py | main.py, points.essential.txt, server.js, store.py |
| Q12 | 1 | 1 | main.py, JS.txt, store.py | main.py, JS.txt, store.py |
| Q13 | 1 | 1 | main.py, store.py, server.js | main.py, server.js, store.py |
| Q14 | 1 | 1 | main.py, store.py, points.essential.txt | main.py, points.essential.txt, store.py |
| Q15 | 1 | 1 | store.py, main.py, server.js | store.py, main.py, server.js |
| Q16 | 1 | 1 | store.py, main.py, server.js, JS.txt | store.py, server.js, main.py, JS.txt |
| Q17 | 2 | 2 | index.js, server.js, main.py, hellonode.js, package.json | store.py, main.py, index.js, server.js, package.json |
| Q18 | 1 | 1 | server.js, package.json, main.py, index.js, hellonode.js | server.js, package.json, main.py, index.js, hellonode.js |
| Q19 | 1 | 1 | package.json, main.py, server.js, points.essential.txt | package.json, main.py, points.essential.txt, server.js |
| Q20 | 1 | 1 | requirements.txt, main.py, points.essential.txt, verse4.txt, server.js | requirements.txt, main.py, points.essential.txt, server.js, verse4.txt |
| Q21 | 1 | 1 | main.py, JS.txt, store.py, requirements.txt | main.py, requirements.txt, JS.txt, store.py |
| Q22 | 1 | 1 | index.js, hellonode.js, package.json, server.js, main.py | index.js, package.json, hellonode.js, server.js, main.py |
| Q23 | 1 | 1 | JS.txt, main.py, points.essential.txt, index.js, server.js | JS.txt, points.essential.txt, Myworld.py, main.py, server.js |
| Q24 | 1 | 1 | points.essential.txt, verse4.txt, main.py, store.py, Myworld.py | points.essential.txt, JS.txt, Myworld.py, verse1.txt, main.py |
| Q25 | 1 | 1 | Myworld.py, JS.txt, points.essential.txt, main.py, store.py | Myworld.py, JS.txt, points.essential.txt, store.py, main.py |
| Q26 | 1 | 1 | Css.html, main.py, index.js, server.js, points.essential.txt | Css.html, main.py, points.essential.txt, server.js, index.js |
| Q27 | 1 | 1 | superheroes.json, main.py, JS.txt, points.essential.txt, server.js | superheroes.json, package.json, main.py, server.js, JS.txt |
| Q28 | 1 | 1 | server.js, main.py, index.js, package.json | main.py, server.js, index.js, package.json |
| Q29 | 1 | 1 | verse1.txt, verse2.txt, verse3.txt, verse4.txt, points.essential.txt | verse1.txt, verse2.txt, verse4.txt, verse3.txt, points.essential.txt |
| Q30 | 1 | 1 | store.py, server.js, main.py | store.py, server.js, main.py |
| Q31 | 1 | 1 | main.py, JS.txt, store.py, points.essential.txt, index.js | main.py, JS.txt, points.essential.txt, index.js, store.py |
| Q32 | 1 | 1 | main.py, points.essential.txt, store.py, requirements.txt, hellonode.js | main.py, requirements.txt, store.py, points.essential.txt, hellonode.js |
| Q33 | 1 | 1 | main.py, server.js, store.py | main.py, store.py, server.js |
| Q34 | 1 | 1 | server.js, store.py, points.essential.txt, hellonode.js, main.py | server.js, store.py, main.py, points.essential.txt, package.json |
| Q35 | 1 | 1 | server.js, package.json, index.js, hellonode.js, main.py | server.js, package.json, main.py, index.js, points.essential.txt |
| Q36 | 1 | 2 | server.js, main.py, package.json, store.py, index.js | package.json, server.js, index.js, main.py, store.py |
| Q37 | 2 | 1 | JS.txt, main.py, Myworld.py, store.py, points.essential.txt | main.py, JS.txt, points.essential.txt, store.py, Myworld.py |
| Q38 | 1 | 1 | points.essential.txt, main.py, store.py, verse4.txt, JS.txt | points.essential.txt, main.py, store.py, JS.txt, verse4.txt |
| Q39 | MISS | MISS | store.py, JS.txt, main.py | store.py, JS.txt, main.py |
| Q40 | 1 | 1 | server.js, store.py, main.py, package.json, index.js | server.js, store.py, main.py, package.json, index.js |
