from fastapi import APIRouter

from .. import schemas

router = APIRouter(
    prefix="/health",
    tags=['Health']
)


@router.get("/", response_model=schemas.HealthOut)
def health():
    """服务健康检查。"""
    return {"status": "ok"}
