from fastapi import APIRouter, Depends, Request

from app.core.config import get_settings
from app.core.security import csrf_token, get_or_create_session
from app.schemas.chat import SessionOut

router = APIRouter(tags=["session"])


@router.get("/session", response_model=SessionOut)
def bootstrap_session(request: Request, _sid: str = Depends(get_or_create_session)):
    return SessionOut(csrf_token=csrf_token(request.state.raw_session), expires_in_days=get_settings().session_ttl_days)
