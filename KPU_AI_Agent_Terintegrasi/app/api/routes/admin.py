import hashlib
import hmac
import json
import logging
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.admin_security import (
    ADMIN_COOKIE,
    ADMIN_CSRF_COOKIE,
    clear_admin_cookie,
    consume_rate_limit,
    get_admin_context,
    hash_password,
    request_client_key,
    require_admin,
    require_admin_csrf,
    require_guest_csrf,
    require_password_change_csrf,
    session_expiration,
    set_admin_cookie,
    verify_password,
)
from app.core.config import get_settings
from app.db.models import (
    AdminAuditLog,
    AdminSession,
    AdminUser,
    IngestionDocument,
    IngestionErrorLog,
    IngestionRun,
    PasswordResetToken,
    utcnow,
)
from app.db.session import get_db
from app.schemas.admin import (
    AdminCsrfOut,
    AdminDocumentOut,
    AdminDocumentsOut,
    AdminErrorOut,
    AdminErrorsOut,
    AdminLoginIn,
    AdminLoginOut,
    AdminMessageOut,
    AdminN8nMonitorOut,
    AdminSummaryOut,
    AdminUserOut,
    ChangePasswordIn,
    ForgotPasswordIn,
    IngestionCallbackIn,
    IngestionCallbackOut,
    ResetPasswordIn,
    RetryOut,
)
from app.services.n8n_monitor import N8nMonitorError, get_n8n_monitoring

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _audit(
    db: Session,
    actor: str | None,
    action: str,
    target_type: str,
    target_id: str,
    details: dict | None = None,
) -> None:
    db.add(
        AdminAuditLog(
            actor_user_id=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=json.dumps(
                details or {}, separators=(",", ":"), ensure_ascii=False
            ),
        )
    )


def _send_reset_email(email: str, token: str) -> None:
    settings = get_settings()
    if not (settings.smtp_host and settings.smtp_from_email):
        raise RuntimeError("SMTP reset belum dikonfigurasi")
    link = f"{settings.admin_reset_url}#token={quote(token)}"
    message = EmailMessage()
    message["Subject"] = "Atur ulang kata sandi Admin KPU"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(
        "Gunakan tautan berikut untuk mengatur ulang kata sandi. Tautan berlaku selama 30 menit "
        "dan hanya dapat digunakan sekali:\n\n"
        + link
        + "\n\nJika Anda tidak meminta ini, abaikan email ini."
    )
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


@router.get("/auth/csrf", response_model=AdminCsrfOut)
def csrf_bootstrap(request: Request, response: Response, db: Session = Depends(get_db)):
    token = secrets.token_urlsafe(32)
    raw_session = request.cookies.get(ADMIN_COOKIE, "")
    if raw_session and len(raw_session) <= 128:
        session = db.get(
            AdminSession,
            hmac.new(
                get_settings().session_secret.encode(),
                raw_session.encode(),
                hashlib.sha256,
            ).hexdigest(),
        )
        if (
            session
            and session.expires_at.replace(
                tzinfo=session.expires_at.tzinfo or utcnow().tzinfo
            )
            > utcnow()
        ):
            session.csrf_hash = hmac.new(
                get_settings().session_secret.encode(),
                token.encode(),
                hashlib.sha256,
            ).hexdigest()
    if db.dirty:
        db.commit()
    settings = get_settings()
    response.set_cookie(
        ADMIN_CSRF_COOKIE,
        token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="strict",
        max_age=600,
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return AdminCsrfOut(csrf_token=token)


@router.post("/auth/login", response_model=AdminLoginOut)
def login(
    payload: AdminLoginIn,
    request: Request,
    response: Response,
    _csrf: None = Depends(require_guest_csrf),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    consume_rate_limit(
        db, "login", request_client_key(request), settings.admin_login_rate_limit
    )
    user = db.scalar(select(AdminUser).where(AdminUser.email == payload.email))
    if (
        not user
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=401, detail="Email atau kata sandi tidak valid."
        )

    raw_session = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    expires_at, max_age = session_expiration()
    db.add(
        AdminSession(
            id=hmac.new(
                settings.session_secret.encode(), raw_session.encode(), hashlib.sha256
            ).hexdigest(),
            user_id=user.id,
            csrf_hash=hmac.new(
                settings.session_secret.encode(), csrf.encode(), hashlib.sha256
            ).hexdigest(),
            expires_at=expires_at,
        )
    )
    _audit(db, user.id, "admin.login", "admin_user", user.id)
    db.commit()
    set_admin_cookie(response, raw_session, max_age)
    response.delete_cookie(
        ADMIN_CSRF_COOKIE, path="/", secure=settings.cookie_secure, samesite="strict"
    )
    return AdminLoginOut(
        csrf_token=csrf,
        user=AdminUserOut(
            id=user.id,
            email=user.email,
            must_change_password=user.must_change_password,
        ),
    )


@router.get("/auth/me", response_model=AdminUserOut)
def current_admin(context=Depends(get_admin_context)):
    user = context[0]
    return AdminUserOut(
        id=user.id, email=user.email, must_change_password=user.must_change_password
    )


@router.post("/auth/logout", status_code=204)
def logout(
    response: Response,
    context=Depends(get_admin_context),
    _user: AdminUser = Depends(require_password_change_csrf),
    db: Session = Depends(get_db),
):
    user, session = context
    db.delete(session)
    _audit(db, user.id, "admin.logout", "admin_user", user.id)
    db.commit()
    clear_admin_cookie(response)
    response.status_code = 204
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/auth/forgot-password", response_model=AdminMessageOut)
def forgot_password(
    payload: ForgotPasswordIn,
    request: Request,
    _csrf: None = Depends(require_guest_csrf),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    consume_rate_limit(
        db, "reset", request_client_key(request), settings.admin_reset_rate_limit
    )
    user = db.scalar(select(AdminUser).where(AdminUser.email == payload.email))
    if user and user.is_active:
        token = secrets.token_urlsafe(32)
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        ).update({PasswordResetToken.used_at: utcnow()}, synchronize_session=False)
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=_token_digest(token),
                expires_at=utcnow() + timedelta(minutes=30),
            )
        )
        db.commit()
        try:
            _send_reset_email(user.email, token)
        except (OSError, smtplib.SMTPException, RuntimeError):
            logger.exception(
                "Pengiriman email reset admin gagal untuk akun yang cocok; token tidak dicatat."
            )
    return AdminMessageOut(
        message="Jika akun cocok, instruksi reset akan dikirim ke email terdaftar."
    )


@router.post("/auth/reset-password", response_model=AdminMessageOut)
def reset_password(
    payload: ResetPasswordIn,
    _csrf: None = Depends(require_guest_csrf),
    db: Session = Depends(get_db),
):
    now = utcnow()
    user_id = db.scalar(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == _token_digest(payload.token),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .values(used_at=now)
        .returning(PasswordResetToken.user_id)
    )
    if not user_id:
        raise HTTPException(
            status_code=400, detail="Token reset tidak valid atau sudah kedaluwarsa."
        )
    user = db.get(AdminUser, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=400, detail="Token reset tidak valid atau sudah kedaluwarsa."
        )
    user.password_hash = hash_password(payload.password)
    user.must_change_password = False
    user.updated_at = utcnow()
    db.query(AdminSession).filter(AdminSession.user_id == user.id).delete(
        synchronize_session=False
    )
    _audit(db, user.id, "admin.password_reset", "admin_user", user.id)
    db.commit()
    return AdminMessageOut(message="Kata sandi berhasil diubah. Silakan masuk kembali.")


@router.post("/auth/change-password", response_model=AdminLoginOut)
def change_password(
    payload: ChangePasswordIn,
    request: Request,
    response: Response,
    context=Depends(get_admin_context),
    user: AdminUser = Depends(require_password_change_csrf),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Kata sandi saat ini tidak valid.")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=422, detail="Kata sandi baru harus berbeda.")
    raw_cookie = request.cookies[ADMIN_COOKIE]
    new_csrf = secrets.token_urlsafe(32)
    session = context[1]
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.updated_at = utcnow()
    session.csrf_hash = hmac.new(
        get_settings().session_secret.encode(), new_csrf.encode(), hashlib.sha256
    ).hexdigest()
    db.query(AdminSession).filter(
        AdminSession.user_id == user.id,
        AdminSession.id != context[1].id,
    ).delete(synchronize_session=False)
    _audit(db, user.id, "admin.password_changed", "admin_user", user.id)
    db.commit()
    _, max_age = session_expiration()
    set_admin_cookie(response, raw_cookie, max_age)
    return AdminLoginOut(
        csrf_token=new_csrf,
        user=AdminUserOut(
            id=user.id,
            email=user.email,
            must_change_password=False,
        ),
    )


@router.get("/dashboard/summary", response_model=AdminSummaryOut)
def dashboard_summary(
    _user: AdminUser = Depends(require_admin), db: Session = Depends(get_db)
):
    grouped = dict(
        db.execute(
            select(IngestionDocument.status, func.count()).group_by(
                IngestionDocument.status
            )
        ).all()
    )
    docs = {
        key: int(grouped.get(key, 0))
        for key in ("success", "pending", "processing", "failed")
    }
    docs["total"] = sum(grouped.values())
    chunks = db.scalar(
        select(func.sum(IngestionDocument.chunks_count)).where(
            IngestionDocument.pinecone_confirmed.is_(True),
            IngestionDocument.chunks_count.is_not(None),
        )
    )
    pasal = db.scalar(
        select(func.sum(IngestionDocument.pasal_count)).where(
            IngestionDocument.pinecone_confirmed.is_(True),
            IngestionDocument.pasal_count.is_not(None),
        )
    )
    last_sync = db.scalar(select(func.max(IngestionDocument.last_processed_at)))
    recent_runs = db.scalars(
        select(IngestionRun)
        .order_by(
            IngestionRun.completed_at.desc().nullslast(),
            IngestionRun.started_at.desc().nullslast(),
        )
        .limit(8)
    ).all()
    recent_errors = db.scalars(
        select(IngestionErrorLog)
        .order_by(
            IngestionErrorLog.occurred_at.desc(),
        )
        .limit(8)
    ).all()
    activities = [
        {
            "type": "run",
            "workflow": run.workflow,
            "status": run.status,
            "at": run.completed_at or run.started_at,
            "execution_id": run.execution_id,
        }
        for run in recent_runs
    ] + [
        {
            "type": "error",
            "workflow": error.workflow,
            "status": error.status,
            "at": error.occurred_at,
            "execution_id": error.execution_id,
        }
        for error in recent_errors
    ]
    activities.sort(
        key=lambda item: (
            item["at"].timestamp() if isinstance(item["at"], datetime) else 0
        ),
        reverse=True,
    )

    workflows: dict[str, dict[str, str | datetime | None]] = {}
    for name in ("WF1", "WF2"):
        run = db.scalar(
            select(IngestionRun)
            .where(IngestionRun.workflow == name)
            .order_by(
                IngestionRun.completed_at.desc().nullslast(),
                IngestionRun.started_at.desc().nullslast(),
            )
            .limit(1)
        )
        workflows[name] = {
            "status": run.status if run else "unknown",
            "last_execution_at": run.completed_at or run.started_at if run else None,
        }
    return AdminSummaryOut(
        documents=docs,
        indexed_chunks=int(chunks) if chunks is not None else None,
        indexed_pasal=int(pasal) if pasal is not None else None,
        last_sync=last_sync,
        workflows=workflows,
        activities=activities[:10],
    )


@router.get("/dashboard/workflows", response_model=AdminN8nMonitorOut)
def dashboard_workflows(_user: AdminUser = Depends(require_admin)):
    try:
        return get_n8n_monitoring()
    except N8nMonitorError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None


@router.get("/dashboard/documents", response_model=AdminDocumentsOut)
def list_documents(
    status: str | None = Query(default=None, max_length=32),
    q: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    _user: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if status and status not in {"pending", "processing", "success", "failed"}:
        raise HTTPException(status_code=422, detail="Filter status tidak valid.")
    query = select(IngestionDocument)
    count_query = select(func.count()).select_from(IngestionDocument)
    if status:
        query = query.where(IngestionDocument.status == status)
        count_query = count_query.where(IngestionDocument.status == status)
    if q:
        term = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        matcher = or_(
            IngestionDocument.title.ilike(f"%{term}%", escape="\\"),
            IngestionDocument.source_url.ilike(f"%{term}%", escape="\\"),
            IngestionDocument.document_number.ilike(f"%{term}%", escape="\\"),
        )
        query = query.where(matcher)
        count_query = count_query.where(matcher)
    items = db.scalars(
        query.order_by(IngestionDocument.updated_at.desc())
        .offset(
            (page - 1) * page_size,
        )
        .limit(page_size)
    ).all()
    return AdminDocumentsOut(
        items=[
            AdminDocumentOut.model_validate(item, from_attributes=True)
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=int(db.scalar(count_query) or 0),
    )


@router.get("/dashboard/errors", response_model=AdminErrorsOut)
def list_errors(
    status: str | None = Query(default=None, max_length=40),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    _user: AdminUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = select(IngestionErrorLog)
    count_query = select(func.count()).select_from(IngestionErrorLog)
    if status:
        query = query.where(IngestionErrorLog.status == status)
        count_query = count_query.where(IngestionErrorLog.status == status)
    rows = db.scalars(
        query.order_by(IngestionErrorLog.occurred_at.desc())
        .offset(
            (page - 1) * page_size,
        )
        .limit(page_size)
    ).all()
    return AdminErrorsOut(
        items=[AdminErrorOut.model_validate(row, from_attributes=True) for row in rows],
        page=page,
        page_size=page_size,
        total=int(db.scalar(count_query) or 0),
    )


@router.post(
    "/dashboard/errors/{error_id}/retry", response_model=RetryOut, status_code=202
)
def retry_error(
    error_id: str,
    request: Request,
    _user: AdminUser = Depends(require_admin_csrf),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    if not settings.admin_retry_webhook_url or not settings.admin_retry_webhook_secret:
        raise HTTPException(
            status_code=503, detail="Webhook retry n8n belum dikonfigurasi."
        )
    error = db.get(IngestionErrorLog, error_id)
    if not error or error.status not in {"failed", "error"} or error.retry_attempts:
        raise HTTPException(
            status_code=409,
            detail="Error tidak tersedia untuk retry atau sudah pernah dicoba.",
        )
    now = utcnow()
    changed = db.execute(
        update(IngestionErrorLog)
        .where(
            IngestionErrorLog.id == error_id,
            IngestionErrorLog.status.in_(("failed", "error")),
            IngestionErrorLog.retry_attempts == 0,
        )
        .values(
            status="retry_requested",
            retry_attempts=1,
            retry_requested_at=now,
        )
    ).rowcount
    if not changed:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Retry sudah diminta oleh operator lain."
        )
    error.status = "retry_requested"
    error.retry_attempts = 1
    error.retry_requested_at = now
    payload = {
        "error_id": error.id,
        "workflow": error.workflow,
        "execution_id": error.execution_id,
        "node": error.node,
        "requested_at": now.isoformat(),
    }
    _audit(db, _user.id, "ingestion.retry_requested", "ingestion_error", error.id)
    db.commit()
    try:
        with httpx.Client(timeout=10) as client:
            result = client.post(
                settings.admin_retry_webhook_url,
                json=payload,
                headers={
                    "X-Admin-Retry-Secret": settings.admin_retry_webhook_secret,
                    "Idempotency-Key": error.id,
                },
            )
    except httpx.HTTPError as exc:
        logger.error(
            "Webhook retry n8n tidak dapat dikonfirmasi (%s); retry tetap dikunci untuk mencegah duplikasi.",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="Status dispatch belum dapat dipastikan; retry dikunci agar tidak duplikat.",
        ) from None
    if result.status_code < 200 or result.status_code >= 300:
        logger.warning(
            "Webhook retry n8n menolak permintaan, HTTP %s.", result.status_code
        )
        raise HTTPException(
            status_code=502, detail="n8n belum mengonfirmasi penerimaan retry."
        )
    try:
        confirmation = result.json()
    except ValueError:
        confirmation = {}
    if confirmation.get("accepted") is not True:
        raise HTTPException(
            status_code=502, detail="n8n belum mengonfirmasi penerimaan retry."
        )
    execution_id = confirmation.get("execution_id")
    if not isinstance(execution_id, str) or not execution_id or len(execution_id) > 128:
        raise HTTPException(
            status_code=502,
            detail="n8n tidak memberikan ID eksekusi untuk konfirmasi retry.",
        )
    error.retry_execution_id = execution_id
    retry_failure = db.scalar(
        select(IngestionErrorLog.id)
        .where(
            IngestionErrorLog.execution_id == execution_id,
            IngestionErrorLog.status.in_(("failed", "error")),
        )
        .limit(1)
    )
    if retry_failure and error.status == "retry_requested":
        error.status = "retry_failed"
        _audit(
            db,
            None,
            "ingestion.retry_failed",
            "ingestion_error",
            error.id,
            {"execution_id": execution_id},
        )
    db.commit()
    return RetryOut(
        status="accepted",
        message="Retry diterima n8n; hasil menunggu konfirmasi workflow.",
        n8n_execution_id=error.retry_execution_id,
    )


@router.post("/ingestion/callback", response_model=IngestionCallbackOut)
def ingestion_callback(
    payload: IngestionCallbackIn,
    x_ingestion_key: str = Header(default="", alias="X-Ingestion-Key"),
    db: Session = Depends(get_db),
):
    configured = get_settings().ingestion_callback_secret
    if not configured or not hmac.compare_digest(x_ingestion_key, configured):
        raise HTTPException(status_code=401, detail="Kunci callback tidak valid.")
    if payload.status == "success" and not payload.pinecone_confirmed:
        raise HTTPException(
            status_code=422,
            detail="Status sukses membutuhkan konfirmasi insert Pinecone.",
        )
    now = utcnow()
    document = db.get(IngestionDocument, payload.document_id)
    if not document:
        document = IngestionDocument(
            id=payload.document_id, source_url=payload.source_url
        )
        db.add(document)
    same_version = document.file_hash == payload.file_hash
    preserve_confirmed = (
        same_version and document.status == "success" and payload.status != "success"
    )
    document.source_url = payload.source_url
    document.document_type = payload.document_type
    document.document_number = payload.document_number
    document.title = payload.title
    document.year = payload.year
    if payload.file_hash is not None:
        document.file_hash = payload.file_hash
    if not preserve_confirmed:
        document.status = payload.status
        document.pinecone_confirmed = (
            payload.pinecone_confirmed if payload.status == "success" else False
        )
        document.namespace = payload.namespace
        document.chunks_count = payload.chunks_count
        document.pasal_count = payload.pasal_count
    elif payload.status == "success":
        document.namespace = payload.namespace
        document.chunks_count = payload.chunks_count
        document.pasal_count = payload.pasal_count
        document.pinecone_confirmed = True
    document.updated_at = now
    if payload.status == "success":
        document.last_processed_at = now

    run = db.scalar(
        select(IngestionRun)
        .where(
            IngestionRun.workflow == payload.workflow,
            IngestionRun.execution_id == payload.execution_id,
        )
        .with_for_update()
    )
    if not run:
        run = IngestionRun(
            workflow=payload.workflow,
            execution_id=payload.execution_id,
            document_id=payload.document_id,
            status=payload.status,
            started_at=now,
            completed_at=now if payload.status != "processing" else None,
        )
        db.add(run)
    elif run.status != "success":
        run.document_id = payload.document_id
        run.status = payload.status
        run.completed_at = now if payload.status != "processing" else None
        run.namespace = payload.namespace
        run.chunks_count = payload.chunks_count
        run.pasal_count = payload.pasal_count
    if payload.retry_error_id and payload.status in {"success", "failed"}:
        retry_status = (
            "retry_succeeded"
            if payload.status == "success" and payload.pinecone_confirmed
            else "retry_failed"
        )
        changed = db.execute(
            update(IngestionErrorLog)
            .where(
                IngestionErrorLog.id == payload.retry_error_id,
                IngestionErrorLog.status == "retry_requested",
                or_(
                    IngestionErrorLog.retry_execution_id.is_(None),
                    IngestionErrorLog.retry_execution_id == payload.execution_id,
                ),
            )
            .values(status=retry_status, retry_execution_id=payload.execution_id)
        ).rowcount
        if changed:
            _audit(
                db,
                None,
                f"ingestion.{retry_status}",
                "ingestion_error",
                payload.retry_error_id,
                {"execution_id": payload.execution_id},
            )
    db.commit()
    return IngestionCallbackOut(
        status=document.status, document_id=payload.document_id, run_id=run.id
    )
