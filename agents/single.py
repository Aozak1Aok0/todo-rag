r"""单 Agent baseline：一个模型 + 全部工具，不做显式路由。

对照 `agents/orchestrator.py` 的 Supervisor + specialist 方案：
- 路由不再是 Supervisor 输出的 JSON，而是「模型选哪个工具」；
- 写操作仍然只生成 proposal，审批边界不变；
- 待办读取仍然走确定性 SQLite，不让模型自己数。

最多 4 次模型调用，避免工具循环失控。
"""

import json
import time

from agents.approvals import create_proposal
from agents.write_planner import parse_proposal
from rag import pipeline
from store import list_todos

MODEL = "deepseek-chat"
MAX_STEPS = 4

SYSTEM = (
    "你是待办与代码库问答的单一 Agent。你可以调用工具，按需选择，不要假装调用。\n\n"
    "规则：\n"
    "- 问待办数量、列表、完成状态 → 调 query_todos；数字必须以工具结果为准，不要自己数。\n"
    "- 问代码、接口、配置、表结构、实现 → 调 answer_docs。\n"
    "- 同时问待办和代码 → 两个工具都调，合并成一条回答，保留文档引用与不确定性。\n"
    "- 新增 / 删除 / 修改待办 → 调 propose_todo_write；它只生成待确认 proposal，"
    "你绝不能声称已经执行。\n"
    "- 删除或修改前如果不知道 id，先调 query_todos；参数不合法就如实告诉用户，不要编造。\n"
    "- 最终回答用中文，简洁，不要复述工具调用过程。"
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_todos",
            "description": "查询待办，返回确定性的计数与列表。需要数量/列表/完成状态时先调它。",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "enum": ["all", "open", "done"],
                        "description": "all=全部，open=未完成，done=已完成",
                    }
                },
                "required": ["filter"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "answer_docs",
            "description": "针对代码库/文档的问题做检索并回答，返回带引用的答案。",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_todo_write",
            "description": (
                "为新增/删除/修改待办生成待确认 proposal，不会真正执行。"
                "delete_todo 和 set_completed 用 todo_id 或 name 指定目标。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add_todo", "delete_todo", "set_completed"],
                    },
                    "name": {
                        "type": "string",
                        "description": "add_todo 的待办内容；其他动作可作为目标名称",
                    },
                    "todo_id": {"type": "integer", "description": "目标待办 id"},
                    "completed": {"type": "boolean", "description": "set_completed 的目标状态"},
                },
                "required": ["action"],
            },
        },
    },
]


def _usage(inp=0, out=0):
    return {"in": int(inp or 0), "out": int(out or 0)}


def _add(a, b):
    return _usage(a.get("in", 0) + b.get("in", 0), a.get("out", 0) + b.get("out", 0))


def _resp_usage(resp):
    u = getattr(resp, "usage", None)
    return _usage(
        getattr(u, "prompt_tokens", 0) if u else 0,
        getattr(u, "completion_tokens", 0) if u else 0,
    )


def _todo_text(mode):
    """与 orchestrator.answer_todos 同一套措辞，保证两边可直接比较。"""
    todos = list_todos()
    if mode == "open":
        selected = [t for t in todos if not t["completed"]]
        title = f"未完成待办共 {len(selected)} 条"
    elif mode == "done":
        selected = [t for t in todos if t["completed"]]
        title = f"已完成待办共 {len(selected)} 条"
    else:
        selected = todos
        title = f"当前共有 {len(todos)} 条待办"

    done = sum(1 for t in todos if t["completed"])
    summary = (
        f"{title}（全部 {len(todos)} 条，未完成 {len(todos) - done} 条，"
        f"已完成 {done} 条）。"
    )
    if not selected:
        return summary + "\n没有符合条件的待办。"
    lines = [
        f"{i}. [{'x' if t['completed'] else ' '}] #{t['id']} {t['name']}"
        for i, t in enumerate(selected, 1)
    ]
    return summary + "\n" + "\n".join(lines)


def _resolve_todo_id(args):
    if args.get("todo_id") is not None:
        try:
            return int(args["todo_id"])
        except (TypeError, ValueError):
            return None
    name = str(args.get("name") or "").strip()
    if not name:
        return None
    for t in list_todos():
        if t["name"] == name:
            return t["id"]
    return None


async def _exec_tool(client, name, args, k, multi_query, state):
    """执行一个工具，返回 (文本结果, usage, 可选 docs 结果)。"""
    if name == "query_todos":
        mode = str(args.get("filter") or "all").strip().lower()
        if mode not in {"all", "open", "done"}:
            mode = "all"
        return _todo_text(mode), _usage(), None

    if name == "answer_docs":
        question = str(args.get("question") or "").strip()
        if not question:
            return "缺少 question 参数。", _usage(), None
        result = await pipeline.answer_verified(
            client, question, k=k, max_revisions=0, multi_query=multi_query
        )
        return result["answer"], result.get("usage") or _usage(), result

    if name == "propose_todo_write":
        action = str(args.get("action") or "").strip()
        payload = {"action": action, "args": {}}
        if action == "add_todo":
            payload["args"]["name"] = str(args.get("name") or "").strip()
        else:
            todo_id = _resolve_todo_id(args)
            if todo_id is not None:
                payload["args"]["todo_id"] = todo_id
            if action == "set_completed":
                payload["args"]["completed"] = bool(args.get("completed", True))
        parsed = parse_proposal(
            json.dumps(payload, ensure_ascii=False), list_todos()
        )
        if parsed.get("action"):
            proposal = create_proposal(
                parsed["action"],
                parsed["args"],
                parsed["summary"],
                parsed.get("reason", ""),
            )
            state["proposal"] = proposal
            return (
                f"已生成待确认 proposal：{parsed['summary']}（id={proposal['id']}）。"
                "写操作尚未执行，需要用户确认。",
                _usage(),
                None,
            )
        clarify = parsed.get("clarify") or "请明确要执行哪个写操作。"
        state["clarify"] = clarify
        return clarify, _usage(), None

    return f"未知工具：{name}", _usage(), None


def _route_of(tools_used):
    docs = "answer_docs" in tools_used
    todo = any(t in tools_used for t in ("query_todos", "propose_todo_write"))
    if docs and todo:
        return "both"
    return "docs" if docs else "todos"


async def run_single_agent(client, question, k=10, multi_query=True):
    """执行一次单 Agent 工具循环，返回与 run_multi_agent 同构的结果。"""
    t_all = time.perf_counter()
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question},
    ]
    usage = _usage()
    trace = []
    tools_used = []
    state = {}
    answer = ""

    for _ in range(MAX_STEPS):
        t0 = time.perf_counter()
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            temperature=0,
        )
        step_usage = _resp_usage(resp)
        usage = _add(usage, step_usage)
        msg = resp.choices[0].message

        tool_calls = list(getattr(msg, "tool_calls", None) or [])
        assistant = {"role": "assistant", "content": msg.content or ""}
        if tool_calls:
            assistant["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {
                        "name": c.function.name,
                        "arguments": c.function.arguments or "{}",
                    },
                }
                for c in tool_calls
            ]
        messages.append(assistant)

        if not tool_calls:
            answer = msg.content or ""
            trace.append({
                "agent": "single",
                "status": "ok",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                **step_usage,
                "detail": "final",
            })
            break

        names = []
        for call in tool_calls:
            name = call.function.name
            names.append(name)
            tools_used.append(name)
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            t1 = time.perf_counter()
            try:
                text, tool_usage, docs = await _exec_tool(
                    client, name, args if isinstance(args, dict) else {}, k, multi_query, state
                )
                status = "ok"
            except Exception as e:  # noqa: BLE001
                text = f"工具执行失败：{type(e).__name__}"
                tool_usage, docs = _usage(), None
                status = "error"
            usage = _add(usage, tool_usage)
            if docs:
                state["docs"] = docs
            state["last_text"] = text
            trace.append({
                "agent": "tool",
                "status": status,
                "latency_ms": int((time.perf_counter() - t1) * 1000),
                **tool_usage,
                "detail": name,
            })
            messages.append({"role": "tool", "tool_call_id": call.id, "content": text})

        if state.get("proposal") and "propose_todo_write" in names:
            # proposal 已经生成，不再继续调用，避免重复 proposal
            answer = state["last_text"]
            break

    if not answer:
        answer = state.get("last_text") or "（没有生成回答）"

    docs_result = state.get("docs") or {}
    proposal = state.get("proposal")
    if proposal:
        status = "approval_required"
    elif state.get("clarify"):
        status = "needs_clarification"
    else:
        status = "ok"

    route = _route_of(tools_used)
    return {
        "answer": answer,
        "status": status,
        "route": route,
        "proposal": proposal,
        "plan": {
            "route": route,
            "intent": "write" if "propose_todo_write" in tools_used else "read",
        },
        "trace": trace,
        "usage": usage,
        "sources": pipeline.format_sources(docs_result.get("hits") or []),
        "verification": docs_result.get("verification"),
        "tools": tools_used,
        "latency_ms": int((time.perf_counter() - t_all) * 1000),
    }
