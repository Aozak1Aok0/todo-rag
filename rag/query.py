r"""查询规划：把用户问题改写成 2–3 条检索式。

动机（实测）：问「启动时有哪些数据」时，代码里对应的是「空表时插种子」，
字面/向量都对不上，`init_db` 块排到 10 名以外。改写查询后它直接到第 1 名。

成本：1 次小调用（约 200–300 input token），失败时回退到原问题。
"""

import json
import re

MODEL = "deepseek-chat"

PLAN_SYSTEM = (
    "你是代码库检索的查询规划器。把用户问题改写成 2–3 条中文检索式："
    "保留原句，其余几条补上代码里可能出现的英文标识符、函数名或术语（如 init_db、SEEDS、CREATE TABLE、"
    "端点、配置项）。不要回答问题，只输出 JSON。"
)


def build_plan_messages(question, n=3):
    user = (
        f"用户问题：{question}\n\n"
        f"请输出 JSON：{{\"queries\": [\"...\"]}}，最多 {n} 条，第一条必须是原问题。"
    )
    return [
        {"role": "system", "content": PLAN_SYSTEM},
        {"role": "user", "content": user},
    ]


def parse_queries(text, question, n=3):
    m = re.search(r"\{.*\}", text or "", re.S)
    if m:
        try:
            data = json.loads(m.group(0))
            qs = [str(x).strip() for x in (data.get("queries") or []) if str(x).strip()]
            if qs:
                out, seen = [], set()
                for q in [question] + qs:
                    if q not in seen:
                        seen.add(q)
                        out.append(q)
                return out[:n]
        except Exception:  # noqa: BLE001
            pass
    return [question]


async def plan_queries(client, question, n=3):
    resp = await client.chat.completions.create(
        model=MODEL,
        messages=build_plan_messages(question, n),
        temperature=0,
    )
    usage = resp.usage
    text = resp.choices[0].message.content or ""
    return parse_queries(text, question, n), {
        "in": usage.prompt_tokens if usage else 0,
        "out": usage.completion_tokens if usage else 0,
    }