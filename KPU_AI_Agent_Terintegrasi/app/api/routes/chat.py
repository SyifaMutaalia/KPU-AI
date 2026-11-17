import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.safety import contains_sensitive_identifiers
from app.core.security import check_rate_limit, require_csrf
from app.db.models import Conversation, Message
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import ai_service
from app.services.history_service import owned_conversation, save_message

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db), sid: str = Depends(require_csrf)):
    if contains_sensitive_identifiers(payload.message):
        raise HTTPException(422, "Jangan masukkan NIK, email, atau nomor telepon. Hapus identitas pribadi dan coba lagi.")
    check_rate_limit(db, sid)
    if payload.conversation_id:
        conversation = owned_conversation(db, payload.conversation_id, sid)
    else:
        conversation = Conversation(session_id=sid, title=payload.message.strip()[:100])
        # Delay creation until the AI operation succeeds.

    history: list[tuple[str, str]] = []
    if payload.conversation_id:
        previous = db.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.created_at.desc()).limit(24)).all()
        history = [(m.role, m.content) for m in reversed(previous)]

    try:
        result = ai_service.answer_question(payload.message.strip(), history)
    except Exception as exc:
        logger.warning("AI request failed: %s", type(exc).__name__)
        raise HTTPException(503, "Layanan AI sedang tidak tersedia. Periksa konfigurasi atau coba kembali.") from None
    if not payload.conversation_id:
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
    save_message(db, conversation, "user", payload.message.strip())
    save_message(db, conversation, "assistant", result.answer, result.sources)
    return ChatResponse(conversation_id=conversation.id, answer=result.answer, sources=result.sources, grounded=result.grounded)
