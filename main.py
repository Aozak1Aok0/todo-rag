# FastAPI 版 todo-api + 大模型接入（DeepSeek，OpenAI 兼容）

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel

from store import add_todo, init_db, list_todos, remove_todo

import obs
import json
import os
import time
import re

# ---------- 1. 应用与本地 /docs（解决国内白屏） ----------

"""
这部分代码配置了FastAPI应用，并解决了国内访问Swagger UI白屏的问题。
通过自定义/docs端点，使用本地静态资源来加载Swagger UI。
"""
app = FastAPI(docs_url=None)  # 初始化FastAPI应用，禁用默认的/docs端点
BASE_DIR = Path(__file__).resolve().parent  # 获取当前文件所在目录
RAG_K = int(os.getenv("RAG_K", "8"))  # /rag 默认检索块数
# 将static目录挂载到/static路径，用于存放静态文件
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    """
    自定义Swagger UI页面，使用本地资源解决国内访问白屏问题
    """
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="Todo + LLM API - Swagger UI",
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
    )


# ---------- 2. SQLite 待办存储（实现见 store.py，Web 与 MCP 共用） ----------
init_db()


# ---------- 3. pydantic 模型 ----------
"""
这部分定义了API请求的数据模型，使用Pydantic进行数据验证。
"""
class TodoCreate(BaseModel):
    """创建待办事项的数据模型"""
    name: str


class ChatRequest(BaseModel):
    # 多轮：前端把整段对话历史传过来，每条是 {"role": "user"|"assistant", "content": "..."}
    messages: list[dict]


class RagRequest(BaseModel):
    question: str
    k: int | None = None


# ---------- 4. 待办接口 ----------
@app.get("/api/todos")
async def get_todos():
    return list_todos()


@app.post("/api/todos", status_code=201)
async def create_todo(todo: TodoCreate):
    name = todo.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name 不能为空")
    return add_todo(name)


@app.delete("/api/todos/{todo_id}")
async def delete_todo(todo_id: int):
    if not remove_todo(todo_id):
        raise HTTPException(status_code=404, detail="not found")
    return {"msg": "deleted", "id": todo_id}


@app.get("/")
async def root():
    return {"msg": "Todo + LLM API 运行中", "ui": "/rag-ui", "docs": "/docs", "stats": "/stats"}


def get_client():
    # 没设置 key 时友好报错，而不是崩在调用处
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="未设置 DEEPSEEK_API_KEY 环境变量")
    return AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")


# ---------- 5. 多轮 + 流式 /chat（SSE） ----------
# 和之前单轮版的区别：前端传完整 messages 历史（多轮）；用 StreamingResponse 把字一个个吐出来（流式）
@app.post("/chat")
async def chat(req: ChatRequest):
    client = get_client()  # 没 key 会在这里返回 500

    async def event_gen():
        stream = await client.chat.completions.create(
            model="deepseek-chat",
            messages=req.messages,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                # 每条 SSE 事件用 JSON 包一层，前端好解析
                yield f"data: {json.dumps({'content': delta.content}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# ---------- 6. Function Calling（Agent 核心） ----------
# 给模型一个工具：查询当前系统的待办列表。模型会自己决定要不要调它 —— 这就是 Agent 的"自主决策"
tools = [
    {
        "type": "function",
        "function": {
            "name": "query_todos",
            "description": "查询当前系统里所有待办事项的列表",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


@app.post("/agent")
async def agent(req: ChatRequest):
    client = get_client()
    messages = list(req.messages)
    resp = await client.chat.completions.create(
        model="deepseek-chat",
        messages=messages,
        tools=tools,
        tool_choice="auto",
    )
    msg = resp.choices[0].message
    # 模型决定调用工具
    if msg.tool_calls:
        for tc in msg.tool_calls:
            if tc.function.name == "query_todos":
                result = {"todos": list_todos()}
                messages.append(msg)  # 必须把"带 tool_call 的助手消息"回传给模型
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        # 第二轮：模型根据工具结果生成最终回答
        resp2 = await client.chat.completions.create(
            model="deepseek-chat", messages=messages
        )
        return {"reply": resp2.choices[0].message.content, "used_tool": True}
    return {"reply": msg.content, "used_tool": False}


# ---------- 7. 手写 ReAct（不依赖 SDK 的 tools 封装） ----------
# 对比 /agent：SDK 版把"调不调工具"交给 tool_choice="auto" 让模型自己决定；
# 这里反过来——我们手写 Reason→Act→Observe 循环：
#   1) 用 system 提示词规定模型输出固定格式（Thought / Action / Action Input / Observation / Final Answer）
#   2) 我们自己用正则解析模型吐出的文本，决定调哪个工具、传什么参数
#   3) 把工具结果拼成 Observation 塞回对话，再让模型继续思考，直到它给出 Final Answer
# 你真正控制了 Agent 的"运行时"，而不是当 SDK 的调包侠。
REACT_SYSTEM_PROMPT = """你是一个使用 ReAct（推理-行动）框架的助手。
请严格按以下格式逐步思考和调用工具：

Thought: 你的推理过程
Action: 工具名称
Action Input: 工具参数（JSON 格式，无参数时写 {}）

环境会返回：
Observation: 工具的执行结果

当你已能回答用户时，输出：
Thought: 我已获得足够信息
Final Answer: 给用户的完整回答

可用工具：
- query_todos：查询系统里所有待办事项，无参数，返回待办列表。

规则：
1. 每次只输出一组 Thought/Action，或一个 Final Answer，不要一次写多个 Action。
2. 若不需要工具就能回答，直接输出 Final Answer。
3. 必须严格使用上述英文格式标记。
"""


def _parse_react(text: str):
    """从模型文本解析动作或最终答案。返回 ('final', answer) | ('action', name, args) | ('none', None)。"""
    m = re.search(r"Final Answer:\s*(.*)", text, re.DOTALL | re.IGNORECASE)
    if m:
        return "final", m.group(1).strip()
    am = re.search(r"Action:\s*([^\n]+)", text, re.IGNORECASE)
    im = re.search(r"Action Input:\s*(\{.*?\})", text, re.DOTALL | re.IGNORECASE)
    if am:
        name = am.group(1).strip()
        args_raw = im.group(1).strip() if im else "{}"
        try:
            args = json.loads(args_raw)
        except json.JSONDecodeError:
            args = {}
        return "action", name, args
    return "none", None


async def _run_react(client, question: str, max_steps: int = 5):
    messages = [
        {"role": "system", "content": REACT_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    trace = []          # 记录每一步，方便你看到循环真的跑了几轮
    answer = None
    used_tool = False
    for step in range(max_steps):
        resp = await client.chat.completions.create(model="deepseek-chat", messages=messages)
        text = resp.choices[0].message.content or ""
        messages.append({"role": "assistant", "content": text})

        kind = _parse_react(text)
        if kind[0] == "final":
            answer = kind[1]
            trace.append({"step": step + 1, "type": "final", "text": text})
            break
        if kind[0] == "action":
            _, name, args = kind
            # 手写工具调度：我们决定调哪个、怎么调（不靠 SDK）
            if name == "query_todos":
                observation = {"todos": list_todos()}
                used_tool = True
            else:
                observation = {"error": f"未知工具: {name}"}
            obs_text = f"Observation: {json.dumps(observation, ensure_ascii=False)}"
            messages.append({"role": "user", "content": obs_text})
            trace.append(
                {"step": step + 1, "type": "action", "action": name,
                 "args": args, "observation": observation}
            )
            continue
        # 模型既没给 Final Answer 也没给 Action：兜底当作它想直接回答
        answer = text.strip()
        trace.append({"step": step + 1, "type": "fallback", "text": text})
        break
    if answer is None:
        answer = "（已达到最大步数仍未给出最终答案）"
    return answer, used_tool, trace


@app.post("/agent-raw", summary="手写 ReAct 版 Agent（不依赖 SDK tools 封装）")
async def agent_raw(req: ChatRequest):
    client = get_client()
    # 取最后一条 user 消息作为问题
    question = ""
    for m in reversed(req.messages):
        if m.get("role") == "user":
            question = m.get("content", "")
            break
    if not question:
        raise HTTPException(status_code=400, detail="messages 里没有 user 消息")
    answer, used_tool, trace = await _run_react(client, question)
    return {"answer": answer, "used_tool": used_tool, "steps": len(trace), "trace": trace}

# ---------- 8. RAG 接口（检索本地语料后回答） ----------
@app.get("/rag-ui", include_in_schema=False)
async def rag_ui():
    """极简演示页（单文件，无 CDN 依赖）。"""
    return FileResponse(BASE_DIR / "static" / "rag.html")

@app.post("/rag", summary="RAG：先检索本地语料再回答，返回 answer + sources")
async def rag(req: RagRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question 不能为空")

    k = RAG_K if req.k is None else req.k   # 注意：k=0 不能用 or，会被当成没传
    if not 1 <= k <= 10:
        raise HTTPException(status_code=400, detail="k 必须在 1..10 之间")

    # 懒加载：没建索引/没装依赖时，基础接口仍然可用
    try:
        from rag.rag import retrieve
        from rag.prompt import build_rag_messages
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"检索层不可用：{type(e).__name__}")

    try:
        # retrieve 是同步的（embedding + chroma），丢到线程池避免卡事件循环
        from starlette.concurrency import run_in_threadpool
        hits = await run_in_threadpool(retrieve, question, k)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"检索失败（先跑 rag/rag.py build）：{type(e).__name__}")

    client = get_client()
    messages = build_rag_messages(question, hits)
    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0,
        )
    except Exception as e:  # noqa: BLE001
        obs.log_event("rag", "POST /rag", ok=False, error=type(e).__name__,
                      latency_ms=int((time.time() - t0) * 1000),
                      k=k, sources=len(hits), question_len=len(question))
        raise HTTPException(status_code=502, detail=f"模型调用失败：{type(e).__name__}")

    usage = resp.usage
    obs.log_event(
        "rag", "POST /rag", ok=True,
        latency_ms=int((time.time() - t0) * 1000),
        tokens_in=usage.prompt_tokens if usage else 0,
        tokens_out=usage.completion_tokens if usage else 0,
        k=k, sources=len(hits), question_len=len(question),
    )
    return {
        "answer": resp.choices[0].message.content or "",
        "k": k,
        "sources": [
            {
                "source": h["source"],
                "start_line": h["start_line"],
                "end_line": h["end_line"],
                "distance": round(h["distance"], 4) if h["distance"] is not None else None,
                "preview": h["text"].split("\n", 1)[-1][:160],
            }
            for h in hits
        ],
        "usage": {
            "in": usage.prompt_tokens if usage else 0,
            "out": usage.completion_tokens if usage else 0,
        },
    }


# ---------- 9. 可观测汇总 ----------
@app.get("/stats", summary="最近 N 天的调用次数 / 耗时 / token / 成本汇总")
async def stats(days: int = 7):
    if not 1 <= days <= 90:
        raise HTTPException(status_code=400, detail="days 必须在 1..90 之间")
    return obs.summarize(days)
