import json
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Conversation, Message, utcnow
from app.schemas.chat import ConversationDetail, ConversationOut, MessageOut, Source


def owned_conversation(db: Session, conversation_id: UUID, session_id: str) -> Conversation:
    result = db.scalar(select(Conversation).where(Conversation.id == str(conversation_id), Conversation.session_id == session_id))
    if not result:
        # Same message for nonexistent and another user's conversations.
        raise HTTPException(404, "Percakapan tidak ditemukan.")
    return result


def save_message(db: Session, conversation: Conversation, role: str, content: str, sources: list[Source] | None = None) -> None:
    db.add(Message(conversation_id=conversation.id, role=role, content=content, sources_json=json.dumps(
        [item.model_dump() for item in (sources or [])], ensure_ascii=False
    )))
    conversation.updated_at = utcnow()
    db.commit()


def list_conversations(db: Session, session_id: str) -> list[ConversationOut]:
    result = db.scalars(select(Conversation).where(Conversation.session_id == session_id).order_by(Conversation.updated_at.desc()).limit(100))
    return [ConversationOut.model_validate(c, from_attributes=True) for c in result]


def detail_conversation(db: Session, conversation: Conversation) -> ConversationDetail:
    messages = db.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at, Message.id)).all()
    return ConversationDetail(
        id=UUID(conversation.id), title=conversation.title,
        created_at=conversation.created_at, updated_at=conversation.updated_at,
        messages=[MessageOut(
            id=UUID(m.id), role=m.role, content=m.content, created_at=m.created_at,
            sources=[Source.model_validate(x) for x in json.loads(m.sources_json)],
        ) for m in messages],
    )
