from fastapi import APIRouter

from agentic_chatbot_hitl_backend import get_all_threads

from .. import schemas

router = APIRouter(
    prefix="/threads",
    tags=['Threads']
)


@router.get("/", response_model=schemas.ThreadsOut)
def list_threads():
    """列出所有对话线程 ID。"""
    return {"threads": get_all_threads()}
