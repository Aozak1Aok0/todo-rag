r"""校验 Agent：独立检查草稿答案是否被检索片段支持。

它**不看**草稿是怎么生成出来的，只看：资料、问题、草稿。
判定口径偏严：资料没直接提到的细节都算 unsupported —— 目的是压幻觉，不是夸答案。
"""

import json
import re

MODEL = "deepseek-chat"
VERIFY_SYSTEM = "你是严格的事实核查员。只依据给定资料判断，不使用资料之外的知识。"


def _context(hits):
    return "\n\n".join(
        f"### 资料 {i} · {h['source']}（第 {h['start_line']}-{h['end_line']} 行）\n{h['text']}"
        for i, h in enumerate(hits, 1)
    )


def build_verify_messages(question, hits, answer):
    user = (
        "以下是检索到的资料：\n\n"
        + _context(hits)
        + f"\n\n问题：{question}\n\n待核查的回答：\n{answer}\n\n"
        "请把回答拆成独立断言，逐条判断是否被资料直接支持，只输出一个 JSON 对象：\n"
        '{"unsupported": ["..."], "verdict": "ok 或 revise", "reason": "一句话"}\n'
        "规则：\n"
        "- 资料没有直接提到的细节，一律算 unsupported（哪怕它可能是真的）\n"
        "- 回答写「资料中没有」且资料确实没有 → 视为 ok\n"
        "- 语义等价但措辞不同，不算错\n"
        "- unsupported 最多列 5 条；没有问题就返回空数组 + ok\n"
    )
    return [
        {"role": "system", "content": VERIFY_SYSTEM},
        {"role": "user", "content": user},
    ]


def parse_verdict(text: str) -> dict:
    """容错解析：模型有时会包 ```json 或加解释。"""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {"unsupported": [], "verdict": "ok", "reason": "解析失败，按 ok 处理", "parsed": False}
    try:
        data = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return {"unsupported": [], "verdict": "ok", "reason": "JSON 解析失败，按 ok 处理", "parsed": False}

    unsupported = [str(x) for x in (data.get("unsupported") or [])][:5]
    verdict = "revise" if (str(data.get("verdict", "")).lower() == "revise" or unsupported) else "ok"
    return {
        "unsupported": unsupported,
        "verdict": verdict,
        "reason": str(data.get("reason") or ""),
        "parsed": True,
    }


async def verify_answer(client, question, hits, answer):
    resp = await client.chat.completions.create(
        model=MODEL,
        messages=build_verify_messages(question, hits, answer),
        temperature=0,
    )
    usage = resp.usage
    out = parse_verdict(resp.choices[0].message.content or "")
    out["usage"] = {
        "in": usage.prompt_tokens if usage else 0,
        "out": usage.completion_tokens if usage else 0,
    }
    return out


def build_revise_messages(question, hits, draft, unsupported):
    """把校验结果作为约束，让回答 Agent 重写一版。"""
    bullets = "\n".join(f"- {x}" for x in unsupported)
    user = (
        "以下是检索到的资料：\n\n"
        + _context(hits)
        + f"\n\n问题：{question}\n\n上一版回答：\n{draft}\n\n"
        "独立校验认为下面这些内容没有被资料支持：\n"
        f"{bullets}\n\n"
        "请重新给出完整回答：删除未被支持的内容，或明确写「资料中没有」；不要用资料之外的知识补充。"
    )
    return [
        {"role": "system", "content": "你是严谨的项目助手。只依据给定资料回答，并保持简洁。"},
        {"role": "user", "content": user},
    ]