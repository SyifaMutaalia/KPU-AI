import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class AnonymousSession(Base):
    __tablename__ = "anonymous_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # salted token digest
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(ForeignKey("anonymous_sessions.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class UsageWindow(Base):
    __tablename__ = "usage_windows"
    session_id: Mapped[str] = mapped_column(ForeignKey("anonymous_sessions.id", ondelete="CASCADE"), primary_key=True)
    minute: Mapped[int] = mapped_column(Integer, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


Index("ix_messages_conversation_created", Message.conversation_id, Message.created_at)


class AdminUser(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "admin"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="admin", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AdminSession(Base):
    __tablename__ = "sessions"
    __table_args__ = {"schema": "admin"}

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("admin.users.id", ondelete="CASCADE"), nullable=False, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = {"schema": "admin"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("admin.users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AdminRateLimit(Base):
    __tablename__ = "rate_limits"
    __table_args__ = (UniqueConstraint("scope", "key_hash", "window", name="uq_admin_rate_scope_key_window"), {"schema": "admin"})

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    window: Mapped[int] = mapped_column(Integer, nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class AdminAuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = {"schema": "admin"}

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("admin.users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class IngestionDocument(Base):
    __tablename__ = "documents"
    __table_args__ = {"schema": "ingestion"}

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    document_type: Mapped[str | None] = mapped_column(String(120))
    document_number: Mapped[str | None] = mapped_column(String(120))
    title: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(Integer)
    file_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    namespace: Mapped[str | None] = mapped_column(String(255))
    last_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chunks_count: Mapped[int | None] = mapped_column(Integer)
    pasal_count: Mapped[int | None] = mapped_column(Integer)
    pinecone_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class IngestionRun(Base):
    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("workflow", "execution_id", name="uq_ingestion_runs_workflow_execution"),
        {"schema": "ingestion"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    execution_id: Mapped[str] = mapped_column(String(128), nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chunks_count: Mapped[int | None] = mapped_column(Integer)
    pasal_count: Mapped[int | None] = mapped_column(Integer)
    namespace: Mapped[str | None] = mapped_column(String(255))


class IngestionErrorLog(Base):
    __tablename__ = "error_logs"
    __table_args__ = (
        UniqueConstraint("workflow", "execution_id", "node", name="uq_ingestion_error_workflow_execution_node"),
        {"schema": "ingestion"},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    workflow: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    execution_id: Mapped[str] = mapped_column(String(128), nullable=False)
    node: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="failed", nullable=False, index=True)
    details: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    retry_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_execution_id: Mapped[str | None] = mapped_column(String(128))
