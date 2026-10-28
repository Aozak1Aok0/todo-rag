r"""Todo 写操作规划器：只生成 proposal，不执行任何写操作。"""

import json
import re

MODEL = "deepseek-chat"

PLANNER_SYSTEM = (
    "你是 Todo 写操作规划器。你的唯一任务是把用户请求转成一个待审批的动作，"
    "绝对不要执行写操作，也不要假装已经完成。只输出 JSON。"
)

ALLOWED_ACTIONS = {"add_todo", "delete_todo", "set_completed"}


def build_messages(question, todos):
    todo_json = json.dumps(todos, ensure_ascii=False)
    user = (
        f"当前待办（id / name / completed）：\n{todo_json}\n\n"
        f"用户请求：{question}\n\n"
        "只输出一个 JSON 对象：\n"
        '{"action":"add_todo|delete_todo|set_completed|null",'
        '"args":{},"reason":"一句话","clarify":"动作不明确时给用户的追问"}\n\n'
        "参数：\n"
        "- add_todo: {\"name\":\"待办内容\"}\n"
        "- delete_todo: {\"todo_id\":123}\n"
        "- set_completed: {\"todo_id\":123,\"completed\":true}\n\n"
        "规则：\n"
        "- 删除/修改必须从上面的待办 id 中选，不能编造 id；\n"
        "- 一次只提议一个动作；批量操作或不明确时 action=null，并在 clarify 说明；\n"
        "- 不要输出解释性 markdown，不要调用工具，不要执行。"
    )
    return [
        {"role": "system", "content": PLANNER_SYSTEM},
        {"role": "user", "content": user},
    ]


def _first_json(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _find_todo(todos, todo_id):
    for t in todos:
        if int(t["id"]) == todo_id:
            return t
    return None


def _clarify(message):
    return {"action": None, "args": {}, "reason": "", "clarify": message}


def parse_proposal(text, todos):
    data = _first_json(text)
    raw_action = str(data.get("action") or "").strip().lower()
    aliases = {
        "add": "add_todo",
        "create_todo": "add_todo",
        "remove_todo": "delete_todo",
        "delete": "delete_todo",
        "update_todo": "set_completed",
        "complete_todo": "set_completed",
        "uncomplete_todo": "set_completed",
    }
    action = aliases.get(raw_action, raw_action)
    if action not in ALLOWED_ACTIONS:
        return _clarify(
            str(data.get("clarify") or "请明确要新增、删除，还是修改某条待办的完成状态。")
        )

    args = data.get("args") if isinstance(data.get("args"), dict) else {}
    reason = str(data.get("reason") or "").strip()

    if action == "add_todo":
        name = str(args.get("name") or "").strip()
        if not name:
            return _clarify("请告诉我要新增的待办内容。")
        if len(name) > 120:
            return _clarify("待办内容太长（最多 120 字），请缩短后再试。")
        return {
            "action": action,
            "args": {"name": name},
            "summary": f"新增待办：「{name}」",
            "reason": reason,
        }

    raw_id = args.get("todo_id")
    if isinstance(raw_id, bool):
        return _clarify("待办 id 不合法，请重新说明。")
    try:
        todo_id = int(raw_id)
    except (TypeError, ValueError):
        return _clarify("请告诉我要操作哪条待办（可以用 id 或名称）。")
    todo = _find_todo(todos, todo_id)
    if todo is None:
        ids = ", ".join(str(t["id"]) for t in todos) or "无"
        return _clarify(f"没有找到待办 #{todo_id}；当前可选 id：{ids}。")

    if action == "delete_todo":
        return {
            "action": action,
            "args": {"todo_id": todo_id},
            "summary": f"删除待办 #{todo_id}：「{todo['name']}」",
            "reason": reason,
        }

    completed = args.get("completed")
    if completed is None:
        completed = {"complete_todo": True, "uncomplete_todo": False}.get(raw_action)
    if not isinstance(completed, bool):
        if completed in (0, 1):
            completed = bool(completed)
        else:
            return _clarify("请说明是标记为已完成还是未完成。")
    return {
        "action": action,
        "args": {"todo_id": todo_id, "completed": completed},
        "summary": (
            f"把待办 #{todo_id}「{todo['name']}」标记为"
            f"{'已完成' if completed else '未完成'}"
        ),
        "reason": reason,
    }


async def propose_write(client, question, todos):
    resp = await client.chat.completions.create(
        model=MODEL,
        messages=build_messages(question, todos),
        temperature=0,
    )
    usage = resp.usage
    parsed = parse_proposal(resp.choices[0].message.content or "", todos)
    return parsed, {
        "in": usage.prompt_tokens if usage else 0,
        "out": usage.completion_tokens if usage else 0,
    }
