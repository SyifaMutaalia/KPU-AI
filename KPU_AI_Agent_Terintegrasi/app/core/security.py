"""Anonymous sessions, ownership, CSRF and basic per-session request caps.

This is application-level protection, NOT an alternative to an edge/WAF IP limit.
"""
import hashlib
import hmac
import secrets
import time
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AnonymousSession, UsageWindow, utcnow
from app.db.session import get_db

COOKIE_NAME = "kpu_session"
CSRF_HEADER = "x-csrf-token"


def session_digest(raw: str) -> str:
    return hmac.new(get_settings().session_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()


def csrf_token(raw: str) -> str:
    return hmac.new(get_settings().session_secret.encode(), ("csrf:" + raw).encode(), hashlib.sha256).hexdigest()


def _set_cookie(response: Response, raw: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=raw,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.session_ttl_days * 86400,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def get_or_create_session(request: Request, response: Response, db: Session = Depends(get_db)) -> str:
    raw = request.cookies.get(COOKIE_NAME, "")
    now = utcnow()
    if raw and len(raw) <= 128:
        record = db.get(AnonymousSession, session_digest(raw))
        if record and record.expires_at.replace(tzinfo=record.expires_at.tzinfo or now.tzinfo) > now:
            request.state.raw_session = raw
            return record.id
    raw = secrets.token_urlsafe(32)
    digest = session_digest(raw)
    record = AnonymousSession(id=digest, expires_at=now + timedelta(days=get_settings().session_ttl_days))
    db.add(record)
    db.commit()
    _set_cookie(response, raw)
    request.state.raw_session = raw
    return digest


def require_csrf(request: Request, session_id: str = Depends(get_or_create_session)) -> str:
    origin = request.headers.get("origin")
    settings = get_settings()
    if origin and origin not in settings.cors_origins:
        raise HTTPException(status_code=403, detail="Origin tidak diizinkan.")
    raw = request.cookies.get(COOKIE_NAME, "")
    if not raw or session_digest(raw) != session_id:
        raise HTTPException(status_code=403, detail="Inisialisasi session terlebih dahulu.")
    incoming = request.headers.get(CSRF_HEADER, "")
    if not incoming or not hmac.compare_digest(incoming, csrf_token(raw)):
        raise HTTPException(status_code=403, detail="CSRF token tidak valid.")
    return session_id


def check_rate_limit(db: Session, session_id: str) -> None:
    minute = int(time.time() // 60)
    maximum = get_settings().chat_rate_limit_per_minute
    # Single atomic UPDATE for existing window; concurrent new-window collisions
    # are handled by the unique (session_id, minute) composite primary key.
    updated = db.execute(
        update(UsageWindow)
        .where(UsageWindow.session_id == session_id, UsageWindow.minute == minute, UsageWindow.count < maximum)
        .values(count=UsageWindow.count + 1)
    ).rowcount
    if not updated:
        try:
            with db.begin_nested():
                db.add(UsageWindow(session_id=session_id, minute=minute, count=1))
                db.flush()
        except IntegrityError:
            # Could be a concurrent insertion OR an exhausted limit.
            db.rollback()
            raise HTTPException(status_code=429, detail="Batas permintaan tercapai, coba lagi nanti.") from None
    db.commit()
