import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.safety import contains_sensitive_identifiers
from app.core.security import check_rate_limit, require_csrf
from app.db.session import get_db
from app.schemas.eppid import DraftOut, DraftRequest
from app.services import draft_service

router = APIRouter(tags=["e-ppid"])
logger = logging.getLogger(__name__)


@router.post("/eppid/draft", response_model=DraftOut)
def draft_eppid(payload: DraftRequest, db: Session = Depends(get_db), sid: str = Depends(require_csrf)):
    if contains_sensitive_identifiers(payload.information_needed + " " + payload.purpose):
        raise HTTPException(422, "Jangan memasukkan data identitas pribadi ke draf.")
    check_rate_limit(db, sid)
    try:
        return draft_service.generate_draft(payload)
    except Exception as exc:
        logger.warning("e-PPID draft generation failed: %s", type(exc).__name__)
        raise HTTPException(503, "Draf belum dapat dibuat saat ini.") from None
