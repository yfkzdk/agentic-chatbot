from typing import Optional

from pydantic import BaseModel


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


class IngestOut(BaseModel):
    """PDF 处理成功响应。"""
    message: str


class HealthOut(BaseModel):
    """健康检查响应。"""
    status: str
