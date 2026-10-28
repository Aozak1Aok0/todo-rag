r"""Supervisor + specialist 多 Agent 编排。

分工：
- Supervisor：只做路由/拆题，不回答业务问题；
- Todo Agent：读操作确定性读 SQLite；写操作只生成待确认 proposal，不直接改库；
- Docs Agent：复用 `rag.pipeline.answer_verified`，即「回答 + 独立校验」；
- Synthesizer：只在 route=both 时合并两个 specialist 的输出，不补充新事实。

这不是无限自治循环：最多 1 次路由 + 1 次文档流水线 + 1 次汇总。
"""

import json
import re
import time

from agents.approvals import create_proposal
from agents.write_planner import propose_write
from rag import pipeline
from store import list_todos

MODEL = "deepseek-chat"
ROUTES = {"todos", "docs", "both"}

SUPERVISOR_SYSTEM = (
    "你是多 Agent 系统的 Supervisor。只做路由和拆题，不回答问题。"
    "可选路由：todos（待办）、docs（代码库文档问答）、both（两者都需要）。"
    "写待办请求只能生成待确认 proposal，绝不能声称已经执行。"
    "只输出 JSON，不要 markdown。"
)

SYNTH_SYSTEM = (
    "你是多 Agent 协调器。只合并下面两个 specialist 的结果，"
    "不要补充它们没有提供的事实；保留文档 Agent 的引用与不确定性。"
)


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


def _first_json(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def is_write_request(question):
    """模型没给 intent 时的保守兜底；真正的写操作仍由写规划器校验。"""
    marks = (
        "添加", "新增", "加到", "加一条", "加个待办", "删除", "删掉",
        "标记为", "改成", "勾选", "完成它", "设为完成", "设为未完成",
    )
    return any(x in (question or "") for x in marks)


def build_supervisor_messages(question):
    user = (
        f"用户问题：{question}\n\n"
        "请输出 JSON：\n"
        '{"route":"todos|docs|both","intent":"read|write","reason":"一句话",'
        '"todos_query":"给待办 Agent 的子问题","docs_query":"给文档 Agent 的子问题"}\n\n'
        "规则：\n"
        "- 只查询待办/完成状态 → todos + intent=read\n"
        "- 新增、删除、修改待办完成状态 → todos + intent=write；只生成 proposal，不执行\n"
        "- 只问代码、接口、实现、配置 → docs\n"
        "- 同时问待办和代码/文档 → both，并把问题拆成两个子问题；有写操作时 intent=write\n"
        "- 不确定时选 docs\n"
        "- 非 both 时，另一个 query 可以为空"
    )
    return [
        {"role": "system", "content": SUPERVISOR_SYSTEM},
        {"role": "user", "content": user},
    ]


def parse_plan(text, question):
    data = _first_json(text)
    route = str(data.get("route") or "docs").strip().lower()
    if route in {"todo", "task", "tasks"}:
        route = "todos"
    if route not in ROUTES:
        route = "docs"
    # 路由 JSON 坏掉时，明确的写请求至少不要误落到文档 Agent
    if not data.get("route") and is_write_request(question):
        route = "todos"

    intent = str(data.get("intent") or "").strip().lower()
    if intent not in {"read", "write"}:
        intent = "write" if is_write_request(question) else "read"
    if route == "docs":
        intent = "read"

    docs_query = str(data.get("docs_query") or "").strip()
    todos_query = str(data.get("todos_query") or "").strip()
    if route in {"docs", "both"} and not docs_query:
        docs_query = question
    if route in {"todos", "both"} and not todos_query:
        todos_query = question

    return {
        "route": route,
        "intent": intent,
        "reason": str(data.get("reason") or "").strip(),
        "todos_query": todos_query,
        "docs_query": docs_query,
    }


async def plan_route(client, question):
    t0 = time.perf_counter()
    resp = await client.chat.completions.create(
        model=MODEL,
        messages=build_supervisor_messages(question),
        temperature=0,
    )
    text = resp.choices[0].message.content or ""
    plan = parse_plan(text, question)
    plan["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    return plan, _resp_usage(resp)


def _todo_filter(question):
    q = question or ""
    if any(x in q for x in ("未完成", "没完成", "没做完", "还没做")):
        return "open"
    if any(x in q for x in ("已完成", "做完了", "完成了")):
        return "done"
    return "all"


def answer_todos(question, todos=None):
    """确定性回答待办，避免模型把待办数量/名称说错。"""
    if is_write_request(question):
        return {
            "answer": "这是一条写操作；写操作必须先由写规划器生成 proposal，"
                      "再由人工确认，不能直接执行。",
            "todos": [],
            "selected": [],
            "write_blocked": True,
        }

    todos = list_todos() if todos is None else list(todos)
    mode = _todo_filter(question)
    count_only = any(x in (question or "") for x in ("多少条", "几条", "数量", "统计"))
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
    summary = f"{title}（全部 {len(todos)} 条，未完成 {len(todos) - done} 条，已完成 {done} 条）。"
    if count_only:
        return {
            "answer": summary,
            "todos": todos,
            "selected": selected,
            "count_only": True,
        }
    if not selected:
        return {"answer": summary + "\n没有符合条件的待办。", "todos": todos, "selected": selected}

    lines = [
        f"{i}. [{'x' if t['completed'] else ' '}] #{t['id']} {t['name']}"
        for i, t in enumerate(selected, 1)
    ]
    return {"answer": summary + "\n" + "\n".join(lines), "todos": todos, "selected": selected}


def build_synth_messages(question, todo_answer, docs_answer):
    user = (
        f"用户问题：{question}\n\n"
        f"待办 Agent 的结果：\n{todo_answer}\n\n"
        f"文档 Agent 的结果：\n{docs_answer}\n\n"
        "请给出一个完整回答。要求：\n"
        "- 分两部分时用「待办」和「文档」小标题；\n"
        "- 不改变待办列表中的名称、id、完成状态；\n"
        "- 不删除文档 Agent 已标注的「资料中没有」或校验不确定性；\n"
        "- 不要补充两个结果之外的新事实。"
    )
    return [
        {"role": "system", "content": SYNTH_SYSTEM},
        {"role": "user", "content": user},
    ]


async def _docs_worker(client, question, k, multi_query):
    return await pipeline.answer_verified(
        client,
        question,
        k=k,
        max_revisions=0,
        multi_query=multi_query,
    )


async def run_multi_agent(client, question, k=10, multi_query=True, docs_worker=None):
    """执行一次 Supervisor + specialist 协作，返回可观测的 trace。"""
    t_all = time.perf_counter()
    plan, plan_usage = await plan_route(client, question)
    route = plan["route"]
    trace = [{
        "agent": "supervisor",
        "status": "ok",
        "latency_ms": plan["latency_ms"],
        **plan_usage,
        "detail": route,
    }]
    total_usage = dict(plan_usage)

    todo_result = None
    docs_result = None
    proposal = None
    errors = {}

    if route in {"todos", "both"}:
        t0 = time.perf_counter()
        agent_name = "todo_planner" if plan["intent"] == "write" else "todos"
        try:
            if plan["intent"] == "write":
                todos = list_todos()
                parsed, planner_usage = await propose_write(
                    client, plan["todos_query"], todos
                )
                total_usage = _add(total_usage, planner_usage)
                if parsed.get("action"):
                    proposal = create_proposal(
                        parsed["action"],
                        parsed["args"],
                        parsed["summary"],
                        parsed.get("reason", ""),
                    )
                    todo_result = {
                        "answer": (
                            f"我准备{parsed['summary']}。"
                            "这是写操作，确认后才会执行。"
                        ),
                        "todos": todos,
                        "selected": [],
                        "proposal": proposal,
                    }
                    detail = parsed["action"]
                else:
                    todo_result = {
                        "answer": parsed.get("clarify") or "请明确要执行哪个写操作。",
                        "todos": todos,
                        "selected": [],
                        "clarify": True,
                    }
                    detail = "clarify"
                trace.append({
                    "agent": agent_name,
                    "status": "ok",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    **planner_usage,
                    "detail": detail,
                })
            else:
                todo_result = answer_todos(plan["todos_query"])
                trace.append({
                    "agent": agent_name,
                    "status": "ok",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "in": 0,
                    "out": 0,
                    "detail": f"{len(todo_result['selected'])}/{len(todo_result['todos'])} 条",
                })
        except Exception as e:  # noqa: BLE001
            errors["todos"] = type(e).__name__
            trace.append({
                "agent": agent_name,
                "status": "error",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "in": 0,
                "out": 0,
                "detail": type(e).__name__,
            })

    if route in {"docs", "both"}:
        t0 = time.perf_counter()
        try:
            worker = docs_worker or _docs_worker
            docs_result = await worker(client, plan["docs_query"], k, multi_query)
            doc_usage = docs_result.get("usage") or _usage()
            total_usage = _add(total_usage, doc_usage)
            trace.append({
                "agent": "docs",
                "status": "ok",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                **doc_usage,
                "detail": f"{len(docs_result.get('hits') or [])} hits",
            })
        except Exception as e:  # noqa: BLE001
            errors["docs"] = type(e).__name__
            trace.append({
                "agent": "docs",
                "status": "error",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "in": 0,
                "out": 0,
                "detail": type(e).__name__,
            })

    if route == "todos":
        if not todo_result:
            raise RuntimeError(f"待办 Agent 失败：{errors.get('todos', 'unknown')}")
        answer = todo_result["answer"]
    elif route == "docs":
        if not docs_result:
            raise RuntimeError(f"文档 Agent 失败：{errors.get('docs', 'unknown')}")
        answer = docs_result["answer"]
    else:
        todo_answer = todo_result["answer"] if todo_result else "待办 Agent 失败。"
        docs_answer = docs_result["answer"] if docs_result else "文档 Agent 失败。"
        if todo_result and docs_result and not proposal and not todo_result.get("clarify"):
            t0 = time.perf_counter()
            try:
                resp = await client.chat.completions.create(
                    model=MODEL,
                    messages=build_synth_messages(question, todo_answer, docs_answer),
                    temperature=0,
                )
                synth_usage = _resp_usage(resp)
                total_usage = _add(total_usage, synth_usage)
                answer = resp.choices[0].message.content or ""
                trace.append({
                    "agent": "synthesizer",
                    "status": "ok",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    **synth_usage,
                    "detail": "merged",
                })
            except Exception as e:  # noqa: BLE001
                errors["synthesizer"] = type(e).__name__
                answer = f"【待办】\n{todo_answer}\n\n【文档】\n{docs_answer}"
                trace.append({
                    "agent": "synthesizer",
                    "status": "error",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "in": 0,
                    "out": 0,
                    "detail": type(e).__name__,
                })
        else:
            answer = f"【待办】\n{todo_answer}\n\n【文档】\n{docs_answer}"

    if proposal:
        status = "approval_required"
    elif todo_result and todo_result.get("clarify"):
        status = "needs_clarification"
    else:
        status = "ok"

    docs_hits = (docs_result or {}).get("hits") or []
    verification = (docs_result or {}).get("verification")
    return {
        "answer": answer,
        "status": status,
        "route": route,
        "proposal": proposal,
        "plan": plan,
        "trace": trace,
        "errors": errors,
        "sources": pipeline.format_sources(docs_hits),
        "verification": verification,
        "rounds": (docs_result or {}).get("rounds", 0),
        "usage": total_usage,
        "latency_ms": int((time.perf_counter() - t_all) * 1000),
    }
