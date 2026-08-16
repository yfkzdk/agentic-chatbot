"""聊天机器人 FastAPI 服务。

轻量外壳：组装各功能路由 → 调用 backend（LangGraph）。
与 app_hitl.py（Streamlit 前端）共用同一套 backend 逻辑。

启动：
    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import chat, threads, ingest, health

app = FastAPI(title="聊天辅助机器人 API")

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(threads.router)
app.include_router(ingest.router)
app.include_router(health.router)
