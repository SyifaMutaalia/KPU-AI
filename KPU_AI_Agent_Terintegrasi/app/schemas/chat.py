from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: UUID | None = None


class Source(BaseModel):
    title: str
    url: str


class ChatResponse(BaseModel):
    conversation_id: UUID
    answer: str
    sources: list[Source] = []
    grounded: bool = False


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime
    sources: list[Source] = []


class ConversationOut(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class SessionOut(BaseModel):
    csrf_token: str
    expires_in_days: int
