r"""RAG 的提示词构造（端点和评测共用同一份，避免两套口径）。"""

import os

SYSTEM = "你是这个项目的代码库问答助手。请准确、简洁地用中文回答。"

RULE_A = ("请仅根据上面的资料回答问题；资料里没有的，请明确说明「资料中没有」，不要编造。")
# 变体 B：允许指出资料本身的错误（Q8 那类"语料纠错"题需要）
RULE_B = RULE_A + (
    "资料本身可能有笔误或与公认事实冲突：遇到这种情况，请明确指出「资料中有误」，并给出正确说法。"
)


# 变体 C：只允许纠「代码标识符/API 名称的拼写」，明确禁止拿外部知识否定资料其余内容
RULE_C = RULE_A + (
    "如果资料中的代码标识符或 API 名称存在明显拼写错误（与该语言的标准库/官方 API 不一致），"
    "请指出并给出正确写法；其它内容一律以资料为准，不要用资料之外的知识去否定资料。"
)


DEFAULT_VARIANT = os.getenv("RAG_PROMPT", "C")  # A=严格 grounding；B=泛化纠错；C=只纠标识符（默认）


def rule_for(variant: str) -> str:
    v = str(variant).upper()
    if v == "B":
        return RULE_B
    if v == "C":
        return RULE_C
    return RULE_A


def build_rag_messages(question: str, hits, variant: str | None = None):
    """把检索到的块拼成 messages。块里已带来源路径和行号。

    variant="A"：只允许依据资料（原口径）
    variant="B"：额外允许指出资料中的笔误（泛化；有假纠正风险）
    variant="C"：只允许纠「代码标识符/API 名称」的拼写（默认）
    不传 variant 时用 DEFAULT_VARIANT（可用环境变量 RAG_PROMPT 覆盖）。
    """
    variant = variant or DEFAULT_VARIANT
    blocks = [
        f"### 资料 {i} · {h['source']}（第 {h['start_line']}-{h['end_line']} 行）\n{h['text']}"
        for i, h in enumerate(hits, 1)
    ]
    user = (
        "以下是检索到的资料片段（可能不完整、也可能有噪声）：\n\n"
        + "\n\n".join(blocks)
        + "\n\n---\n"
        + rule_for(variant) + "\n\n"
        f"问题：{question}"
    )
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
    ]