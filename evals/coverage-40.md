# rerank 评测 20261104-1341

- 池：20 · top-5 · 题数：40 · 模型：`BAAI/bge-reranker-base`
- 变体：base（生产顺序）vs rerank（纯排序，不还原点名文件的置顶规则）

| 指标 | base | rerank | Δ |
|---|---|---|---|
| hit@1 | 34 | 34 | +0.000 |
| hit@3 | 39 | 39 | +0.000 |
| hit@5 | 39 | 39 | +0.000 |
| mrr | 0.912 | 0.912 | +0.000 |
| ndcg@5 | 0.933 | 0.933 | +0.000 |
| coverage | 0.975 | 0.975 | +0.000 |
| all_gold | 39 | 39 | +0.000 |
| chunk@1 | 34 | 34 | +0.000 |
| chunk@3 | 39 | 39 | +0.000 |
| chunk_mrr | 0.904 | 0.904 | +0.000 |

## 逐题

| 题 | base 名次 | rerank 名次 | base top5 | rerank top5 |
|---|---|---|---|---|
| Q1 | 1 | 1 | main.py, store.py, server.js, requirements.txt | main.py, store.py, server.js, requirements.txt |
| Q2 | 1 | 1 | main.py, server.js, Css.html | main.py, server.js, Css.html |
| Q3 | 2 | 2 | server.js, main.py, store.py | server.js, main.py, store.py |
| Q4 | 2 | 2 | server.js, main.py, points.essential.txt, store.py | server.js, main.py, points.essential.txt, store.py |
| Q5 | 1 | 1 | requirements.txt, verse4.txt, verse2.txt, points.essential.txt, main.py | requirements.txt, verse4.txt, verse2.txt, points.essential.txt, main.py |
| Q6 | 1 | 1 | main.py, store.py, points.essential.txt, JS.txt, server.js | main.py, store.py, points.essential.txt, JS.txt, server.js |
| Q7 | 1 | 1 | server.js, main.py, package.json, store.py, index.js | server.js, main.py, package.json, store.py, index.js |
| Q8 | 1 | 1 | JS.txt, verse4.txt, verse2.txt, verse3.txt, main.py | JS.txt, verse4.txt, verse2.txt, verse3.txt, main.py |
| Q9 | 2 | 2 | server.js, main.py, store.py, hellonode.js, index.js | server.js, main.py, store.py, hellonode.js, index.js |
| Q10 | 1 | 1 | main.py, store.py, server.js | main.py, store.py, server.js |
| Q11 | 1 | 1 | main.py, points.essential.txt, server.js, store.py | main.py, points.essential.txt, server.js, store.py |
| Q12 | 1 | 1 | main.py, JS.txt, store.py | main.py, JS.txt, store.py |
| Q13 | 1 | 1 | main.py, store.py, server.js | main.py, store.py, server.js |
| Q14 | 1 | 1 | main.py, store.py, points.essential.txt | main.py, store.py, points.essential.txt |
| Q15 | 1 | 1 | store.py, main.py, server.js | store.py, main.py, server.js |
| Q16 | 1 | 1 | store.py, main.py, server.js, JS.txt | store.py, main.py, server.js, JS.txt |
| Q17 | 2 | 2 | index.js, server.js, main.py, hellonode.js, package.json | index.js, server.js, main.py, hellonode.js, package.json |
| Q18 | 1 | 1 | server.js, package.json, main.py, index.js, hellonode.js | server.js, package.json, main.py, index.js, hellonode.js |
| Q19 | 1 | 1 | package.json, main.py, server.js, points.essential.txt | package.json, main.py, server.js, points.essential.txt |
| Q20 | 1 | 1 | requirements.txt, main.py, points.essential.txt, verse4.txt, server.js | requirements.txt, main.py, points.essential.txt, verse4.txt, server.js |
| Q21 | 1 | 1 | main.py, JS.txt, store.py, requirements.txt | main.py, JS.txt, store.py, requirements.txt |
| Q22 | 1 | 1 | hellonode.js, index.js, package.json, server.js, main.py | hellonode.js, index.js, package.json, server.js, main.py |
| Q23 | 1 | 1 | JS.txt, main.py, points.essential.txt, index.js, server.js | JS.txt, main.py, points.essential.txt, index.js, server.js |
| Q24 | 1 | 1 | points.essential.txt, verse4.txt, main.py, store.py, Myworld.py | points.essential.txt, verse4.txt, main.py, store.py, Myworld.py |
| Q25 | 1 | 1 | Myworld.py, JS.txt, points.essential.txt, main.py, store.py | Myworld.py, JS.txt, points.essential.txt, main.py, store.py |
| Q26 | 1 | 1 | Css.html, main.py, index.js, server.js, points.essential.txt | Css.html, main.py, index.js, server.js, points.essential.txt |
| Q27 | 1 | 1 | superheroes.json, main.py, JS.txt, points.essential.txt, server.js | superheroes.json, main.py, JS.txt, points.essential.txt, server.js |
| Q28 | 1 | 1 | server.js, main.py, index.js, package.json | server.js, main.py, index.js, package.json |
| Q29 | 1 | 1 | verse1.txt, verse2.txt, verse3.txt, verse4.txt, points.essential.txt | verse1.txt, verse2.txt, verse3.txt, verse4.txt, points.essential.txt |
| Q30 | 1 | 1 | store.py, server.js, main.py | store.py, server.js, main.py |
| Q31 | 1 | 1 | main.py, JS.txt, store.py, points.essential.txt, index.js | main.py, JS.txt, store.py, points.essential.txt, index.js |
| Q32 | 1 | 1 | main.py, points.essential.txt, store.py, requirements.txt, hellonode.js | main.py, points.essential.txt, store.py, requirements.txt, hellonode.js |
| Q33 | 1 | 1 | main.py, server.js, store.py | main.py, server.js, store.py |
| Q34 | 1 | 1 | server.js, store.py, points.essential.txt, hellonode.js, main.py | server.js, store.py, points.essential.txt, hellonode.js, main.py |
| Q35 | 1 | 1 | server.js, package.json, index.js, hellonode.js, main.py | server.js, package.json, index.js, hellonode.js, main.py |
| Q36 | 1 | 1 | server.js, main.py, package.json, store.py, index.js | server.js, main.py, package.json, store.py, index.js |
| Q37 | 2 | 2 | JS.txt, main.py, Myworld.py, store.py, points.essential.txt | JS.txt, main.py, Myworld.py, store.py, points.essential.txt |
| Q38 | 1 | 1 | points.essential.txt, main.py, store.py, verse4.txt, JS.txt | points.essential.txt, main.py, store.py, verse4.txt, JS.txt |
| Q39 | MISS | MISS | store.py, JS.txt, main.py | store.py, JS.txt, main.py |
| Q40 | 1 | 1 | server.js, store.py, main.py, package.json, index.js | server.js, store.py, main.py, package.json, index.js |
