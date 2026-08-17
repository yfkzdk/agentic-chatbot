from typing import Optional
from datetime import datetime

from pydantic import BaseModel, EmailStr


# ========================= 认证 =========================

class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ========================= 聊天 =========================

class ChatRequest(BaseModel):
    """对话请求。thread_id 不传时自动创建新对话。"""
    message: str
    thread_id: Optional[str] = None


class ResumeRequest(BaseModel):
    """HITL 审批请求：decision 为 "yes" / "no"。"""
    thread_id: str
    decision: str


class ThreadsOut(BaseModel):
    """对话线程列表响应。"""
    threads: list[str]


# ========================= 其他 =========================

class IngestOut(BaseModel):
    """PDF 处理成功响应。"""
    message: str


class HealthOut(BaseModel):
    """健康检查响应。"""
    status: str
