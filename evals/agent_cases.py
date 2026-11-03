"""多 Agent 与单 Agent 共用的评测用例。"""

CASES = [
    {
        "id": "E1",
        "question": "Swagger 白屏是怎么解决的？",
        "route": "docs",
        "keywords": ["Swagger"],
    },
    {
        "id": "E2",
        "question": "todos 表里有哪些字段？",
        "route": "docs",
        "keywords": ["id", "name", "completed"],
    },
    {
        "id": "E3",
        "question": "现在一共有多少条待办？",
        "route": "todos",
        "keywords": ["3"],
    },
    {
        "id": "E4",
        "question": "现在有多少条待办？顺便说明 Swagger 白屏怎么解决",
        "route": "both",
        "keywords": ["待办", "Swagger"],
    },
    {
        "id": "E5",
        "question": "把「多 Agent 评测」加到待办",
        "route": "todos",
        "intent": "write",
        "action": "add_todo",
        "name": "多 Agent 评测",
    },
    {
        "id": "E6",
        "question": "把「多 Agent 评测」标记为已完成",
        "route": "todos",
        "intent": "write",
        "action": "set_completed",
        "name": "多 Agent 评测",
        "completed": True,
    },
    {
        "id": "E7",
        "question": "删除「多 Agent 评测」这条待办",
        "route": "todos",
        "intent": "write",
        "action": "delete_todo",
        "name": "多 Agent 评测",
    },
    {
        "id": "E8",
        "question": "删除 9999 号待办",
        "route": "todos",
        "intent": "write",
        "clarify": True,
    },
]
