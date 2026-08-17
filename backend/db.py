from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from .settings import settings

# ========================= 引擎 & 会话 =========================

# SQLAlchemy 引擎（SQLite 默认；切换 PostgreSQL 只改 settings.database_url）
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依赖：每次请求一个独立会话，结束后关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ========================= 表模型 =========================

class User(Base):
    """用户：研发知识助手的使用者。"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False, unique=True, index=True)
    password = Column(String, nullable=False)  # bcrypt 哈希
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Conversation(Base):
    """对话归属：把 LangGraph 的 thread_id 关联到具体用户。

    AI 消息内容仍由 LangGraph checkpoint 管理，本表只记录
    "这个 thread 属于谁"，用于多用户隔离。
    """

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(String, nullable=False, unique=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, default="新对话")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuditEvent(Base):
    """安全审计事件：记录谁在什么时候做了什么。"""

    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, index=True)
    event_type = Column(String, nullable=False)
    detail = Column(String, nullable=True)  # 只存非敏感摘要，不存原始消息
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def write_audit(db, event_type: str, user_id=None, detail: str = None):
    """写入一条审计事件（同步提交，审计不可丢）。"""
    event = AuditEvent(user_id=user_id, event_type=event_type, detail=detail)
    db.add(event)
    db.commit()
