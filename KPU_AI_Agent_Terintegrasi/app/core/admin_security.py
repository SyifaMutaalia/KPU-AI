import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AdminRateLimit, AdminSession, AdminUser, utcnow
from app.db.session import get_db

ADMIN_COOKIE = "kpu_admin_session"
ADMIN_CSRF_COOKIE = "kpu_admin_csrf"
CSRF_HEADER = "x-csrf-token"


def _digest(value: str) -> str:
    return hmac.new(
        get_settings().session_secret.encode(), value.encode(), hashlib.sha256
    ).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=2**15,
        r=8,
        p=1,
        maxmem=64 * 1024 * 1024,
        dklen=32,
    )
    return f"scrypt$32768$8$1${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = stored.split("$")
        if algorithm != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            maxmem=64 * 1024 * 1024,
            dklen=len(bytes.fromhex(digest_hex)),
        )
        return hmac.compare_digest(derived.hex(), digest_hex)
    except (ValueError, TypeError, OverflowError):
        return False


def require_guest_csrf(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in get_settings().cors_origins:
        raise HTTPException(status_code=403, detail="Origin tidak diizinkan.")
    cookie = request.cookies.get(ADMIN_CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="Token CSRF tidak valid.")


def get_admin_context(
    request: Request,
    db: Session = Depends(get_db),
) -> tuple[AdminUser, AdminSession]:
    raw = request.cookies.get(ADMIN_COOKIE, "")
    if not raw or len(raw) > 128:
        raise HTTPException(status_code=401, detail="Autentikasi admin diperlukan.")
    session = db.get(AdminSession, _digest(raw))
    now = utcnow()
    if (
        not session
        or session.expires_at.replace(tzinfo=session.expires_at.tzinfo or now.tzinfo)
        <= now
    ):
        if session:
            db.delete(session)
            db.commit()
        raise HTTPException(
            status_code=401, detail="Sesi admin tidak valid atau kedaluwarsa."
        )
    user = db.get(AdminUser, session.user_id)
    if not user or not user.is_active or user.role != "admin":
        raise HTTPException(status_code=403, detail="Akses admin tidak diizinkan.")
    return user, session


def require_admin(context=Depends(get_admin_context)) -> AdminUser:
    user = context[0]
    if user.must_change_password:
        raise HTTPException(
            status_code=403,
            detail="Ganti kata sandi awal sebelum mengakses layanan admin.",
        )
    return user


def _validate_admin_csrf(
    request: Request, context: tuple[AdminUser, AdminSession]
) -> AdminUser:
    user, session = context
    header = request.headers.get(CSRF_HEADER, "")
    if not header or not hmac.compare_digest(_digest(header), session.csrf_hash):
        raise HTTPException(status_code=403, detail="Token CSRF tidak valid.")
    origin = request.headers.get("origin")
    if origin and origin not in get_settings().cors_origins:
        raise HTTPException(status_code=403, detail="Origin tidak diizinkan.")
    return user


def require_admin_csrf(
    request: Request,
    context=Depends(get_admin_context),
) -> AdminUser:
    user = _validate_admin_csrf(request, context)
    if user.must_change_password:
        raise HTTPException(
            status_code=403,
            detail="Ganti kata sandi awal sebelum mengakses layanan admin.",
        )
    return user


def require_password_change_csrf(
    request: Request,
    context=Depends(get_admin_context),
) -> AdminUser:
    return _validate_admin_csrf(request, context)


def consume_rate_limit(db: Session, scope: str, key: str, maximum: int) -> None:
    now = int(time.time())
    window = now // 60
    hashed_key = _digest(f"{scope}:{key}")
    db.execute(
        delete(AdminRateLimit).where(
            AdminRateLimit.scope == scope,
            AdminRateLimit.window < window - 2,
        )
    )
    values = {
        "id": secrets.token_hex(18),
        "scope": scope,
        "key_hash": hashed_key,
        "window": window,
        "count": 1,
    }
    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    statement = (
        insert(AdminRateLimit)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["scope", "key_hash", "window"],
            set_={"count": AdminRateLimit.count + 1},
        )
    )
    db.execute(statement)
    count = db.scalar(
        select(AdminRateLimit.count).where(
            AdminRateLimit.scope == scope,
            AdminRateLimit.key_hash == hashed_key,
            AdminRateLimit.window == window,
        )
    )
    db.commit()
    if count is not None and count > maximum:
        raise HTTPException(
            status_code=429, detail="Terlalu banyak permintaan. Coba lagi nanti."
        )


def request_client_key(request: Request) -> str:
    client = request.client.host if request.client else "unknown"
    return client[:128]


def set_admin_cookie(response: Response, raw: str, max_age: int) -> None:
    settings = get_settings()
    response.set_cookie(
        ADMIN_COOKIE,
        raw,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=max_age,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def clear_admin_cookie(response: Response) -> None:
    response.delete_cookie(
        ADMIN_COOKIE,
        path="/",
        secure=get_settings().cookie_secure,
        httponly=True,
        samesite=get_settings().cookie_samesite,
    )


def session_expiration() -> tuple[datetime, int]:
    max_age = get_settings().admin_session_ttl_hours * 3600
    return utcnow() + timedelta(seconds=max_age), max_age
