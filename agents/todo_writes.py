r"""执行已审批的 Todo 写操作。只应在人工确认后被调用。"""

from agents.approvals import ProposalConflict
from store import add_todo, get_todo, remove_todo, set_completed


def execute_proposal(proposal):
    action = proposal.get("action")
    args = proposal.get("args") or {}

    if action == "add_todo":
        name = str(args.get("name") or "").strip()
        if not name:
            raise ProposalConflict("待办内容为空")
        todo = add_todo(name)
        return {"message": f"已新增待办 #{todo['id']}：「{todo['name']}」", "todo": todo}

    if action == "delete_todo":
        todo_id = int(args.get("todo_id"))
        todo = get_todo(todo_id)
        if todo is None:
            raise ProposalConflict(f"待办 #{todo_id} 已不存在")
        if not remove_todo(todo_id):
            raise ProposalConflict(f"待办 #{todo_id} 删除失败")
        return {"message": f"已删除待办 #{todo_id}：「{todo['name']}」", "todo": todo}

    if action == "set_completed":
        todo_id = int(args.get("todo_id"))
        completed = bool(args.get("completed"))
        if get_todo(todo_id) is None:
            raise ProposalConflict(f"待办 #{todo_id} 已不存在")
        if not set_completed(todo_id, completed):
            raise ProposalConflict(f"待办 #{todo_id} 更新失败")
        return {
            "message": (
                f"已把待办 #{todo_id} 标记为"
                f"{'已完成' if completed else '未完成'}"
            ),
            "todo": get_todo(todo_id),
        }

    raise ProposalConflict(f"未知动作：{action}")
