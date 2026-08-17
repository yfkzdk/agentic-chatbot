"""向后兼容 shim：重新导出 backend 包的公开接口。

保留此文件，让 app_hitl.py 与 fastapi/main.py 的
`from agentic_chatbot_hitl_backend import ...` 无需任何改动。
"""
from backend import chatbot, get_all_threads, get_pending_interrupt, delete_thread, get_conversation_messages, ingest_rag_document

__all__ = ["chatbot", "get_all_threads", "get_pending_interrupt", "delete_thread", "get_conversation_messages", "ingest_rag_document"]
