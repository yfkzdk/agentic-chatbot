import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from agentic_chatbot_hitl_backend import chatbot, get_pending_interrupt

from backend import db as models
from backend.db import get_db, write_audit
from api.dependencies.auth import get_current_user

from .. import schemas

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    tags=['Chat']
)


# ========================= 响应序列化 =========================

def _to_sse(data: dict) -> str:
    """字典 → SSE data 行。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_headers(thread_id: str) -> dict:
    """SSE 必需响应头：禁用网关/代理缓冲，保证逐字输出。"""
    return {
        "X-Thread-ID": thread_id,
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        "Connection": "keep-alive",
    }


def _chat_stream(thread_id, message=None, command=None):
    """生成器：普通对话传 message，HITL 恢复传 command。

    说明：StreamingResponse 会自动将同步生成器放入线程池执行，不阻塞事件循环，
    因此这里无需改用 chatbot.astream（那需要 AsyncSqliteSaver + aiosqlite）。

    事件格式：
        {"type": "text",      "content": "..."}   AI 文本增量
        {"type": "tool",      "name": "...", "content": "..."}  工具调用/结果
        {"type": "hitl",      ...}               需要人工审批
        {"type": "done"}                          流结束
        {"type": "error",    "detail": "..."}    出错
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
                # 只发文本增量，前端负责拼接
                if chunk.content:
                    yield _to_sse({"type": "text", "content": chunk.content})
            elif isinstance(chunk, ToolMessage):
                yield _to_sse({
                    "type": "tool",
                    "name": getattr(chunk, "name", "tool"),
                    "content": chunk.content,
                })

        # 流结束后检查是否触发 HITL 审批（如股票购买等敏感操作）
        pending = get_pending_interrupt(thread_id)
        if pending is not None:
            payload = pending.value if isinstance(pending.value, dict) else {"prompt": str(pending.value)}
            yield _to_sse({"type": "hitl", **payload})

        yield _to_sse({"type": "done"})

    except Exception:
        # 记录完整 traceback 到日志，只向前端返回脱敏后的错误信息
        logger.exception("chat stream 执行失败 thread_id=%s", thread_id)
        yield _to_sse({"type": "error", "detail": "对话处理失败，请稍后重试"})


# ========================= 接口 =========================

@router.post("/stream")
def chat_stream(
    request: schemas.ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """流式对话（SSE）。thread_id 为空时生成新对话 ID 并归属当前用户。"""
    thread_id = request.thread_id or uuid.uuid4().hex

    # 会话归属：新会话自动登记；已有会话校验所有权
    conv = db.query(models.Conversation).filter(
        models.Conversation.thread_id == thread_id
    ).first()

    if conv is None:
        if request.thread_id is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="对话不存在",
            )
        conv = models.Conversation(thread_id=thread_id, owner_id=current_user.id)
        db.add(conv)
        db.commit()
    elif conv.owner_id != current_user.id:
        # 不暴露对话存在性，统一 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话不存在",
        )

    # 审计：记录对话事件（只存摘要，不存消息原文）
    write_audit(
        db,
        "chat_message",
        user_id=current_user.id,
        detail=f"对话 {thread_id[:12]}… 发送消息",
    )

    return StreamingResponse(
        _chat_stream(thread_id, message=request.message),
        media_type="text/event-stream",
        headers=_sse_headers(thread_id),
    )


@router.post("/resume")
def chat_resume(
    request: schemas.ResumeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """HITL 审批恢复：decision 为 "yes" 批准 / "no" 拒绝。"""
    decision = request.decision
    if decision not in ("yes", "no"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="decision 只能是 yes 或 no",
        )

    # 校验会话归属
    conv = db.query(models.Conversation).filter(
        models.Conversation.thread_id == request.thread_id
    ).first()
    if conv is None or conv.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话不存在",
        )

    # 幂等性：必须先存在待处理的中断，否则拒绝恢复
    pending = get_pending_interrupt(request.thread_id)
    if pending is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该对话当前无需人工审批或已处理",
        )

    return StreamingResponse(
        _chat_stream(
            request.thread_id,
            command=Command(resume={"decision": decision}),
        ),
        media_type="text/event-stream",
        headers=_sse_headers(request.thread_id),
    )
