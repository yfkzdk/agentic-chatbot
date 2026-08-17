"""聊天机器人 FastAPI 服务。

轻量外壳：组装各功能路由 → 调用 backend（LangGraph）。
与 app_hitl.py（Streamlit 前端）共用同一套 backend 逻辑。

启动：
    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db import Base, engine
from backend import db as models  # 确保模型注册到 Base.metadata
from backend.settings import settings

from .routers import auth, chat, threads, ingest, health

app = FastAPI(title="聊天辅助机器人 API")


# ========================= 启动事件 =========================

@app.on_event("startup")
def on_startup():
    """启动时校验配置 + 建表。"""
    settings.validate_required()
    Base.metadata.create_all(bind=engine)


# ========================= CORS =========================

origins = settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(threads.router)
app.include_router(ingest.router)
app.include_router(health.router)
