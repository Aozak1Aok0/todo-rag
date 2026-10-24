r"""双 Agent 流水线：检索 + 回答 → 独立校验 →（必要时）重写 → 复核。

与 `/rag` 的区别：多了一次「只看资料和答案」的校验，以及一次可选的重写。
代价是每题多 1–2 次模型调用。
"""

import anyio

from rag.prompt import build_rag_messages
from rag.rag import retrieve
from rag.verify import build_revise_messages, verify_answer

MODEL = "deepseek-chat"


def _usage(inp=0, out=0):
    return {"in": int(inp or 0), "out": int(out or 0)}


def _add(a, b):
    return _usage(a.get("in", 0) + b.get("in", 0), a.get("out", 0) + b.get("out", 0))


def format_sources(hits):
    out = []
    for h in hits:
        out.append({
            "source": h["source"],
            "start_line": h["start_line"],
            "end_line": h["end_line"],
            "distance": round(h["distance"], 4) if h["distance"] is not None else None,
            "preview": h["text"].split("\n", 1)[-1][:160],
        })
    return out


async def answer_once(client, question, k=8, variant=None):
    hits = await anyio.to_thread.run_sync(retrieve, question, k)
    resp = await client.chat.completions.create(
        model=MODEL,
        messages=build_rag_messages(question, hits, variant),
        temperature=0,
    )
    usage = resp.usage
    return {
        "answer": resp.choices[0].message.content or "",
        "hits": hits,
        "usage": _usage(usage.prompt_tokens if usage else 0, usage.completion_tokens if usage else 0),
    }


async def answer_verified(client, question, k=8, max_revisions=1, variant=None):
    first = await answer_once(client, question, k, variant)
    hits = first["hits"]
    usage = dict(first["usage"])
    answer = first["answer"]

    check = await verify_answer(client, question, hits, answer)
    usage = _add(usage, check["usage"])
    rounds = 1

    if check["verdict"] == "revise" and check["unsupported"] and max_revisions > 0:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=build_revise_messages(question, hits, answer, check["unsupported"]),
            temperature=0,
        )
        u = resp.usage
        usage = _add(usage, _usage(u.prompt_tokens if u else 0, u.completion_tokens if u else 0))
        answer = resp.choices[0].message.content or ""
        rounds = 2

        final = await verify_answer(client, question, hits, answer)
        usage = _add(usage, final["usage"])
        final["first_pass"] = {
            "verdict": check["verdict"],
            "unsupported": check["unsupported"],
            "reason": check["reason"],
        }
        check = final

    return {
        "answer": answer,
        "hits": hits,
        "verification": check,
        "rounds": rounds,
        "usage": usage,
    }