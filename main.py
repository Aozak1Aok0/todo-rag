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
RAG_VERIFY_K = int(os.getenv("RAG_VERIFY_K", "10"))  # /rag-verify 默认：多查询 + 更大 k，覆盖 SEEDS/init_db
# 将static目录挂载到/static路径，用于存放静态文件
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# 前端（React）构建产物存在时挂到 /app；开发时用 `npm run dev`（Vite 代理到 :8000）
WEB_DIST = BASE_DIR / "web" / "dist"
if WEB_DIST.is_dir():
    app.mount("/app", StaticFiles(directory=WEB_DIST, html=True), name="app")


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


class RagVerifyRequest(BaseModel):
    question: str
    k: int | None = None
    max_revisions: int = 0   # 默认只报告校验结果，不自动重写（见 docs/dual-agent.md）
    multi_query: bool = True  # 先改写查询再检索（实测 hit@1 9/10、MRR 0.95）


class MultiAgentRequest(BaseModel):
    question: str
    k: int | None = None
    multi_query: bool = True


class ApprovalRequest(BaseModel):
    proposal_id: str
    approved: bool


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
    return {
        "msg": "Todo + LLM API 运行中",
        "ui": "/rag-ui",
        "docs": "/docs",
        "stats": "/stats",
        "multi_agent": "/multi-agent",
        "multi_agent_approve": "/multi-agent/approve",
    }


def _api_key() -> str | None:
    """环境变量优先；Windows 上回退到凭据管理器，免去每次开终端设 key。"""
    key = os.getenv("DEEPSEEK_API_KEY")
    if key:
        return key
    try:
        from credentials import get_deepseek_key

        return get_deepseek_key()
    except Exception:  # noqa: BLE001 —— 非 Windows 或凭据不存在
        return None


def get_client():
    # 没 key 时友好报错，而不是崩在调用处
    api_key = _api_key()
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="未找到 DeepSeek API key：设置环境变量 DEEPSEEK_API_KEY，"
                   "或在 Windows 凭据管理器创建通用凭据 WorkBuddy/DeepSeek",
        )
    return AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")


# ---------- 5. 多轮 + 流式 /chat（SSE） ----------
# 和之前单轮版的区别：前端传完整 messages 历史（多轮）；用 StreamingResponse 把字一个个吐出来（流式）
@app.post("/chat")
async def chat(req: ChatRequest):
    client = get_client()  # 没 key 会在这里返回 500
    t0 = time.time()

    async def event_gen():
        try:
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
            obs.log_event("chat", "POST /chat", ok=True,
                          latency_ms=int((time.time() - t0) * 1000),
                          messages=len(req.messages))
        except Exception as e:  # noqa: BLE001
            obs.log_event("chat", "POST /chat", ok=False, error=type(e).__name__,
                          latency_ms=int((time.time() - t0) * 1000),
                          messages=len(req.messages))
            raise

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
    t0 = time.time()
    tin = tout = 0
    used_tool = False
    try:
        messages = list(req.messages)
        resp = await client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        tin += resp.usage.prompt_tokens if resp.usage else 0
        tout += resp.usage.completion_tokens if resp.usage else 0
        msg = resp.choices[0].message
        if msg.tool_calls:
            used_tool = True
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
            resp2 = await client.chat.completions.create(
                model="deepseek-chat", messages=messages
            )
            tin += resp2.usage.prompt_tokens if resp2.usage else 0
            tout += resp2.usage.completion_tokens if resp2.usage else 0
            reply = resp2.choices[0].message.content
        else:
            reply = msg.content
    except Exception as e:  # noqa: BLE001
        obs.log_event("agent", "POST /agent", ok=False, error=type(e).__name__,
                      latency_ms=int((time.time() - t0) * 1000), used_tool=used_tool)
        raise

    obs.log_event("agent", "POST /agent", ok=True,
                  latency_ms=int((time.time() - t0) * 1000),
                  tokens_in=tin, tokens_out=tout, used_tool=used_tool)
    return {"reply": reply, "used_tool": used_tool}


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


async def _run_react(client, question: str, max_steps: int = 5, usage: dict | None = None):
    messages = [
        {"role": "system", "content": REACT_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    trace = []          # 记录每一步，方便你看到循环真的跑了几轮
    answer = None
    used_tool = False
    for step in range(max_steps):
        resp = await client.chat.completions.create(model="deepseek-chat", messages=messages)
        if usage is not None and getattr(resp, "usage", None):
            usage["in"] = usage.get("in", 0) + (resp.usage.prompt_tokens or 0)
            usage["out"] = usage.get("out", 0) + (resp.usage.completion_tokens or 0)
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

    t0 = time.time()
    usage = {"in": 0, "out": 0}
    try:
        answer, used_tool, trace = await _run_react(client, question, usage=usage)
    except Exception as e:  # noqa: BLE001
        obs.log_event("agent", "POST /agent-raw", ok=False, error=type(e).__name__,
                      latency_ms=int((time.time() - t0) * 1000))
        raise

    obs.log_event("agent", "POST /agent-raw", ok=True,
                  latency_ms=int((time.time() - t0) * 1000),
                  tokens_in=usage["in"], tokens_out=usage["out"],
                  used_tool=used_tool, steps=len(trace))
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


# ---------- 9. 双 Agent：回答 + 独立校验 ----------
@app.post("/rag-verify", summary="双 Agent：检索回答 + 独立校验（必要时重写）")
async def rag_verify(req: RagVerifyRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question 不能为空")

    k = RAG_VERIFY_K if req.k is None else req.k
    if not 1 <= k <= 12:
        raise HTTPException(status_code=400, detail="k 必须在 1..12 之间")
    if not 0 <= req.max_revisions <= 2:
        raise HTTPException(status_code=400, detail="max_revisions 必须在 0..2 之间")

    client = get_client()
    t0 = time.time()
    try:
        from rag import pipeline

        result = await pipeline.answer_verified(client, question, k, req.max_revisions, multi_query=req.multi_query)
    except Exception as e:  # noqa: BLE001
        obs.log_event("rag_verify", "POST /rag-verify", ok=False, error=type(e).__name__,
                      latency_ms=int((time.time() - t0) * 1000), k=k)
        raise HTTPException(status_code=502, detail=f"校验流水线失败：{type(e).__name__}")

    v = result["verification"]
    obs.log_event(
        "rag_verify", "POST /rag-verify", ok=True,
        latency_ms=int((time.time() - t0) * 1000),
        tokens_in=result["usage"]["in"], tokens_out=result["usage"]["out"],
        k=k, rounds=result["rounds"],
        verdict=v.get("verdict"),
        unsupported=len(v.get("unsupported") or []),
    )
    return {
        "answer": result["answer"],
        "k": k,
        "rounds": result["rounds"],
        "verification": v,
        "sources": pipeline.format_sources(result["hits"]),
        "usage": result["usage"],
    }


# ---------- 10. 多 Agent：Supervisor → Todo / Docs →（必要时）汇总 ----------
@app.post("/multi-agent", summary="多 Agent：Supervisor 路由到待办/文档 specialist")
async def multi_agent(req: MultiAgentRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question 不能为空")

    k = RAG_VERIFY_K if req.k is None else req.k
    if not 1 <= k <= 12:
        raise HTTPException(status_code=400, detail="k 必须在 1..12 之间")

    client = get_client()
    t0 = time.time()
    try:
        from agents.orchestrator import run_multi_agent

        result = await run_multi_agent(
            client, question, k=k, multi_query=req.multi_query
        )
    except Exception as e:  # noqa: BLE001
        obs.log_event(
            "multi_agent", "POST /multi-agent", ok=False,
            error=type(e).__name__,
            latency_ms=int((time.time() - t0) * 1000),
            k=k,
        )
        raise HTTPException(status_code=502, detail=f"多 Agent 调用失败：{type(e).__name__}")

    obs.log_event(
        "multi_agent", "POST /multi-agent", ok=True,
        latency_ms=int((time.time() - t0) * 1000),
        tokens_in=result["usage"]["in"],
        tokens_out=result["usage"]["out"],
        k=k,
        route=result["route"],
        agents=len(result["trace"]),
        errors=len(result["errors"]),
    )
    return result


# ---------- 10b. 人工确认后才执行 Todo 写操作 ----------
@app.post("/multi-agent/approve", summary="确认/取消多 Agent 生成的待办写操作")
async def approve_multi_agent(req: ApprovalRequest):
    proposal_id = req.proposal_id.strip()
    if not proposal_id:
        raise HTTPException(status_code=400, detail="proposal_id 不能为空")

    from agents.approvals import (
        ProposalConflict,
        ProposalExpired,
        ProposalNotFound,
        cancel_proposal,
        consume_proposal,
    )
    from agents.todo_writes import execute_proposal

    t0 = time.time()
    if not req.approved:
        try:
            proposal = cancel_proposal(proposal_id)
        except ProposalNotFound:
            raise HTTPException(status_code=404, detail="proposal 不存在、已使用或已取消")
        except ProposalExpired:
            raise HTTPException(status_code=410, detail="proposal 已过期，请重新发起")
        obs.log_event(
            "multi_agent", "POST /multi-agent/approve", ok=True,
            latency_ms=int((time.time() - t0) * 1000),
            status="cancelled", action=proposal["action"],
        )
        return {
            "status": "cancelled",
            "proposal_id": proposal_id,
            "summary": proposal["summary"],
        }

    try:
        proposal = consume_proposal(proposal_id)
        try:
            result = execute_proposal(proposal)
        except (ProposalConflict, TypeError, ValueError) as e:
            obs.log_event(
                "multi_agent", "POST /multi-agent/approve", ok=False,
                error="conflict",
                latency_ms=int((time.time() - t0) * 1000),
                status="conflict", action=proposal["action"],
            )
            raise HTTPException(status_code=409, detail=f"执行失败：{e}")
    except ProposalNotFound:
        raise HTTPException(status_code=404, detail="proposal 不存在、已使用或已取消")
    except ProposalExpired:
        raise HTTPException(status_code=410, detail="proposal 已过期，请重新发起")

    obs.log_event(
        "multi_agent", "POST /multi-agent/approve", ok=True,
        latency_ms=int((time.time() - t0) * 1000),
        status="executed", action=proposal["action"],
    )
    return {
        "status": "executed",
        "proposal_id": proposal_id,
        "action": proposal["action"],
        "result": result,
        "todos": list_todos(),
    }


# ---------- 11. 可观测汇总 ----------
@app.get("/stats-ui", include_in_schema=False)
async def stats_ui():
    """可观测面板（单文件，无 CDN 依赖）。"""
    return FileResponse(BASE_DIR / "static" / "stats.html")


@app.get("/stats", summary="最近 N 天的调用次数 / 耗时 / token / 成本汇总")
async def stats(days: int = 7):
    if not 1 <= days <= 90:
        raise HTTPException(status_code=400, detail="days 必须在 1..90 之间")
    return obs.summarize(days)
