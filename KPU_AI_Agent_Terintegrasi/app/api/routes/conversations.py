from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.security import get_or_create_session, require_csrf
from app.db.session import get_db
from app.schemas.chat import ConversationDetail, ConversationOut
from app.services.history_service import detail_conversation, list_conversations, owned_conversation

router = APIRouter(tags=["conversations"])


@router.get("/conversations", response_model=list[ConversationOut])
def all_conversations(db: Session = Depends(get_db), sid: str = Depends(get_or_create_session)):
    return list_conversations(db, sid)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def one_conversation(conversation_id: UUID, db: Session = Depends(get_db), sid: str = Depends(get_or_create_session)):
    return detail_conversation(db, owned_conversation(db, conversation_id, sid))


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: UUID, db: Session = Depends(get_db), sid: str = Depends(require_csrf)):
    conversation = owned_conversation(db, conversation_id, sid)
    db.delete(conversation)
    db.commit()
    return Response(status_code=204)
