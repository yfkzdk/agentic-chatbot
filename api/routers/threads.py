from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from agentic_chatbot_hitl_backend import delete_thread, get_conversation_messages

from backend import db as models
from backend.db import get_db
from api.dependencies.auth import get_current_user

from .. import schemas

router = APIRouter(
    prefix="/threads",
    tags=['Threads']
)


def _get_owned_conversation(thread_id: str, db: Session, user: models.User):
    """校验会话归属，返回 Conversation；不归属则 404。"""
    conv = db.query(models.Conversation).filter(
        models.Conversation.thread_id == thread_id
    ).first()
    if conv is None or conv.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="对话不存在",
        )
    return conv


@router.get("/", response_model=schemas.ThreadsOut)
def list_threads(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """列出当前用户自己的对话线程。"""
    conversations = db.query(models.Conversation).filter(
        models.Conversation.owner_id == current_user.id
    ).all()
    return {"threads": [c.thread_id for c in conversations]}


@router.get("/{thread_id}/messages")
def get_messages(
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """读取当前用户某个对话的历史消息（用于前端渲染）。"""
    _get_owned_conversation(thread_id, db, current_user)

    messages = get_conversation_messages(thread_id)
    result = []
    for msg in messages:
        role = type(msg).__name__
        if role == "HumanMessage":
            result.append({"role": "user", "content": msg.content})
        elif role in ("AIMessage", "AIMessageChunk"):
            if msg.content:
                result.append({"role": "assistant", "content": msg.content})
        # ToolMessage / 其他类型不展示给前端
    return {"messages": result}


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """删除当前用户自己的一个对话线程。"""
    conv = _get_owned_conversation(thread_id, db, current_user)

    # 删除归属记录 + LangGraph checkpoint
    db.delete(conv)
    db.commit()
    delete_thread(thread_id)
    return None
