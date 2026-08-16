"""聊天机器人 FastAPI 服务。

轻量外壳：接收 HTTP 请求 → 调用 backend（LangGraph）→ 流式返回。
与 app_hitl.py（Streamlit 前端）共用同一套 backend 逻辑。

启动：
    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""
import json
import os
import tempfile
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from agentic_chatbot_hitl_backend import (
    chatbot,
    get_all_threads,
    get_pending_interrupt,
    ingest_rag_document
)

app = FastAPI(title="聊天辅助机器人 API")


# ========================= 请求模型 =========================

class ChatRequest(BaseModel):
    """对话请求。thread_id 不传时自动创建新对话。"""
    message: str
    thread_id: Optional[str] = None


class ResumeRequest(BaseModel):
    """HITL 审批：decision 为 "yes" / "no"。"""
    thread_id: str
    decision: str


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


# ========================= 对话接口 =========================

@app.get("/threads")
def list_threads():
    """列出所有对话线程 ID。"""
    return {"threads": get_all_threads()}


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


@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    """流式对话（SSE）。thread_id 为空时生成新对话 ID。"""
    thread_id = request.thread_id or str(os.urandom(16).hex())
    headers = {"X-Thread-ID": thread_id}
    return StreamingResponse(
        _chat_stream(thread_id, message=request.message),
        media_type="text/event-stream",
        headers=headers,
    )


@app.post("/chat/resume")
def chat_resume(request: ResumeRequest):
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


# ========================= PDF 上传 =========================

@app.post("/ingest", status_code=status.HTTP_201_CREATED)
def ingest_pdf(file: UploadFile = File(...)):
    """上传 PDF 并建立向量索引（供 rag_tool 检索）。"""
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="只支持 PDF 文件",
        )

    temp_path = None
    try:

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".pdf"
        ) as temp_file:

            temp_file.write(file.file.read())
            temp_path = temp_file.name

        ingest_rag_document(temp_path)

        return {"message": f"{file.filename} 处理成功"}

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF 处理失败: {error}",
        )

    finally:
        # 处理完成后删除临时 PDF 文件
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# ========================= 健康检查 =========================

@app.get("/health")
def health():
    """服务健康检查。"""
    return {"status": "ok"}
