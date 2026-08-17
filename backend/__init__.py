import os

from dotenv import load_dotenv


# ============================================================
# LangSmith 追踪 — 必须在所有 LangChain import 之前设置
# ============================================================
load_dotenv(override=True)
if os.getenv("LANGSMITH_TRACING", "false").lower() == "true":
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGSMITH_API_KEY", "")
    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGSMITH_PROJECT", "agentic-chatbot")
    os.environ["LANGCHAIN_ENDPOINT"] = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")


# 依赖顺序：基础设施(db) → rag → tools → graph
from . import db
from . import rag
from . import tools
from . import graph

from .db import User, Conversation, AuditEvent
from .graph import chatbot, get_all_threads, get_pending_interrupt, delete_thread, get_conversation_messages
from .rag import ingest_rag_document

__all__ = [
    "chatbot",
    "get_all_threads",
    "get_pending_interrupt",
    "delete_thread",
    "get_conversation_messages",
    "ingest_rag_document",
    "db",
    "User",
    "Conversation",
    "AuditEvent",
]
