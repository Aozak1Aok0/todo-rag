r"""多查询检索：规划 → 每条检索 → RRF 融合。

不改动单查询的 `retrieve()`；这里只做"多问几遍再合并"。
"""

import anyio

from rag.query import plan_queries
from rag.rag import retrieve

RRF_K = 60


def _fuse(ranked_lists, k):
    fused, by_id = {}, {}
    for hits in ranked_lists:
        for rank, h in enumerate(hits, 1):
            cid = h["id"]
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank)
            by_id.setdefault(cid, h)
    order = sorted(fused, key=lambda cid: -fused[cid])[:k]
    out = []
    for cid in order:
        h = dict(by_id[cid])
        h["score"] = fused[cid]
        out.append(h)
    return out


async def retrieve_multi(client, question, k=8, n_queries=3):
    """返回 (hits, usage)。client 为 None 时退化为单查询。"""
    if client is None or n_queries <= 1:
        hits = await anyio.to_thread.run_sync(retrieve, question, k)
        return hits, {"in": 0, "out": 0}

    queries, usage = await plan_queries(client, question, n_queries)
    pool = max(k * 2, 12)
    ranked = []
    for q in queries:
        ranked.append(await anyio.to_thread.run_sync(retrieve, q, pool))
    return _fuse(ranked, k), usage