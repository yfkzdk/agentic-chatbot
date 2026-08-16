import json
import os

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from agentic_chatbot_hitl_backend import chatbot, get_pending_interrupt

from .. import schemas

router = APIRouter(
    prefix="/chat",
    tags=['Chat']
)


# ========================= 响应序列化 =========================

def _message_to_dict(msg):
    """LangChain 消息 → 前端友好的字典。"""
    return {
        "role": type(msg).__name__,
        "content": msg.content,
        "tool_calls": getattr(msg, "tool_calls", None),
        "name": getattr(msg, "name", None),
    }


def _to_sse(data: dict) -> str:
    """字典 → SSE data 行。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_chunk(type_: str, message):
    """消息 → SSE 事件块。"""
    return _to_sse({"type": type_, "message": _message_to_dict(message)})


def _chat_stream(thread_id, message=None, command=None):
    """共用生成器：普通对话传 message，HITL 恢复传 command。

    事件格式：
        {"type": "text",     "message": {...}}  AI 文本增量
        {"type": "tool",     "message": {...}}  工具调用/结果
        {"type": "hitl",     "prompt": "..."}   需要人工审批
        {"type": "done"}                         流结束
        {"type": "error",   "detail": "..."}    出错
    """
    config = {
        "configurable": {"thread_id": thread_id},
        "run_name": "chat_api",
    }

    # 普通对话：输入用户消息；恢复：携带人工决策继续执行
    graph_input = (
        {"messages": [HumanMessage(content=message)]}
        if command is None
        else command
    )

    try:
        for chunk, _metadata in chatbot.stream(
            graph_input,
            config=config,
            stream_mode="messages",
        ):

            if isinstance(chunk, AIMessage):
                yield _sse_chunk("text", chunk)
            elif isinstance(chunk, ToolMessage):
                yield _sse_chunk("tool", chunk)

        # 流结束后检查是否触发 HITL 审批（股票购买等敏感操作）
        pending = get_pending_interrupt(thread_id)
        if pending is not None:
            yield _to_sse({"type": "hitl", "prompt": str(pending.value)})

        yield _to_sse({"type": "done"})

    except Exception as error:
        yield _to_sse({"type": "error", "detail": str(error)})


# ========================= 接口 =========================

@router.post("/stream")
def chat_stream(request: schemas.ChatRequest):
    """流式对话（SSE）。thread_id 为空时生成新对话 ID。"""
    thread_id = request.thread_id or str(os.urandom(16).hex())
    headers = {"X-Thread-ID": thread_id}
    return StreamingResponse(
        _chat_stream(thread_id, message=request.message),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post("/resume")
def chat_resume(request: schemas.ResumeRequest):
    """HITL 审批恢复：decision 为 "yes" 批准 / "no" 拒绝。"""
    decision = request.decision
    if decision not in ("yes", "no"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="decision 只能是 yes 或 no",
        )

    return StreamingResponse(
        _chat_stream(request.thread_id, command=Command(resume=decision)),
        media_type="text/event-stream",
    )
