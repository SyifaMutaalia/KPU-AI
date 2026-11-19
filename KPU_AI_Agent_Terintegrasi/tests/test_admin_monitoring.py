import hashlib
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.admin_security import hash_password
from app.core.config import get_settings
from app.db.models import (
    AdminAuditLog,
    AdminUser,
    IngestionDocument,
    IngestionErrorLog,
    PasswordResetToken,
    utcnow,
)
from app.db.session import get_engine

INITIAL_PASSWORD = "Initial-Admin-Password-1"


def create_admin(email="admin@example.org", must_change=True):
    with Session(get_engine()) as db:
        user = AdminUser(
            email=email,
            password_hash=hash_password(INITIAL_PASSWORD),
            role="admin",
            is_active=True,
            must_change_password=must_change,
        )
        db.add(user)
        db.commit()
        return user.id


def login(client, email="admin@example.org", password=INITIAL_PASSWORD):
    csrf_response = client.get("/api/v1/admin/auth/csrf")
    assert csrf_response.status_code == 200
    response = client.post(
        "/api/v1/admin/auth/login",
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": csrf_response.json()["csrf_token"]},
    )
    return response


def test_admin_auth_requires_csrf_and_first_password_change(client):
    create_admin()
    csrf = client.get("/api/v1/admin/auth/csrf").json()["csrf_token"]
    assert (
        client.post(
            "/api/v1/admin/auth/login",
            json={
                "email": "admin@example.org",
                "password": INITIAL_PASSWORD,
            },
        ).status_code
        == 403
    )

    response = client.post(
        "/api/v1/admin/auth/login",
        json={
            "email": "admin@example.org",
            "password": INITIAL_PASSWORD,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.json()["user"]["must_change_password"] is True
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.get("/api/v1/admin/dashboard/summary").status_code == 403

    change_token = response.json()["csrf_token"]
    changed = client.post(
        "/api/v1/admin/auth/change-password",
        json={
            "current_password": INITIAL_PASSWORD,
            "new_password": "New-Admin-Password-2026",
        },
        headers={"X-CSRF-Token": change_token},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["user"]["must_change_password"] is False
    assert client.get("/api/v1/admin/dashboard/summary").status_code == 200
    assert (
        client.post(
            "/api/v1/admin/auth/logout",
            headers={
                "X-CSRF-Token": changed.json()["csrf_token"],
            },
        ).status_code
        == 204
    )
    assert client.get("/api/v1/admin/auth/me").status_code == 401


def test_admin_endpoints_require_login_and_retry_is_audited(client, monkeypatch):
    assert client.get("/api/v1/admin/dashboard/errors").status_code == 401
    admin_id = create_admin(must_change=False)
    auth = login(client)
    assert auth.status_code == 200
    csrf = auth.json()["csrf_token"]
    with Session(get_engine()) as db:
        error = IngestionErrorLog(
            workflow="WF1",
            execution_id="exec-1",
            node="Pinecone",
            message="upsert gagal",
            status="failed",
            details='{"reason":"timeout"}',
        )
        db.add(error)
        db.commit()
        error_id = error.id

    monkeypatch.setenv("ADMIN_RETRY_WEBHOOK_URL", "http://n8n.internal/retry")
    monkeypatch.setenv("ADMIN_RETRY_WEBHOOK_SECRET", "test-retry-key")
    get_settings.cache_clear()

    class FakeResponse:
        status_code = 202

        @staticmethod
        def json():
            return {"accepted": True, "execution_id": "n8n-retry-1"}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, json, headers):
            assert url == "http://n8n.internal/retry"
            assert headers["Idempotency-Key"] == error_id
            assert json["execution_id"] == "exec-1"
            return FakeResponse()

    monkeypatch.setattr("app.api.routes.admin.httpx.Client", FakeClient)
    retried = client.post(
        f"/api/v1/admin/dashboard/errors/{error_id}/retry",
        headers={"X-CSRF-Token": csrf},
    )
    assert retried.status_code == 202, retried.text
    assert retried.json()["status"] == "accepted"
    duplicate = client.post(
        f"/api/v1/admin/dashboard/errors/{error_id}/retry",
        headers={"X-CSRF-Token": csrf},
    )
    assert duplicate.status_code == 409
    with Session(get_engine()) as db:
        saved = db.get(IngestionErrorLog, error_id)
        assert saved.status == "retry_requested"
        assert saved.retry_execution_id == "n8n-retry-1"
        audit = db.scalar(
            select(AdminAuditLog).where(
                AdminAuditLog.actor_user_id == admin_id,
                AdminAuditLog.action == "ingestion.retry_requested",
            )
        )
        assert audit is not None


def test_forgot_password_is_non_enumerating_and_reset_token_is_one_time(
    client, monkeypatch
):
    user_id = create_admin(must_change=False)
    assert login(client).status_code == 200
    issued = {}
    monkeypatch.setattr(
        "app.api.routes.admin._send_reset_email",
        lambda email, token: issued.update(email=email, token=token),
    )

    csrf = client.get("/api/v1/admin/auth/csrf").json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf}
    known = client.post(
        "/api/v1/admin/auth/forgot-password",
        json={
            "email": "admin@example.org",
        },
        headers=headers,
    )
    unknown = client.post(
        "/api/v1/admin/auth/forgot-password",
        json={
            "email": "missing@example.org",
        },
        headers=headers,
    )
    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert issued["email"] == "admin@example.org"

    with Session(get_engine()) as db:
        reset = db.scalar(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user_id)
        )
        assert reset.token_hash == hashlib.sha256(issued["token"].encode()).hexdigest()
        assert issued["token"] not in reset.token_hash

    reset_response = client.post(
        "/api/v1/admin/auth/reset-password",
        json={
            "token": issued["token"],
            "password": "Reset-Admin-Password-2026",
        },
        headers=headers,
    )
    assert reset_response.status_code == 200, reset_response.text
    repeated = client.post(
        "/api/v1/admin/auth/reset-password",
        json={
            "token": issued["token"],
            "password": "Another-Admin-Password-2026",
        },
        headers=headers,
    )
    assert repeated.status_code == 400
    expired_token = "expired-token-for-test-that-is-long-enough"
    with Session(get_engine()) as db:
        db.add(
            PasswordResetToken(
                user_id=user_id,
                token_hash=hashlib.sha256(expired_token.encode()).hexdigest(),
                expires_at=utcnow() - timedelta(minutes=1),
            )
        )
        db.commit()
    expired = client.post(
        "/api/v1/admin/auth/reset-password",
        json={
            "token": expired_token,
            "password": "Expired-Admin-Password-2026",
        },
        headers=headers,
    )
    assert expired.status_code == 400
    assert client.get("/api/v1/admin/auth/me").status_code == 401


def test_monitoring_api_and_ingestion_callback_confirm_only_pinecone_success(
    client, monkeypatch
):
    create_admin(must_change=False)
    auth = login(client)
    assert auth.status_code == 200
    monkeypatch.setenv("INGESTION_CALLBACK_SECRET", "test-ingestion-key")
    get_settings.cache_clear()
    payload = {
        "workflow": "WF1",
        "execution_id": "workflow-exec-123",
        "status": "success",
        "document_id": "doc-2026",
        "source_url": "https://jdih.kpu.go.id/doc/2026",
        "document_type": "pkpu",
        "document_number": "1",
        "title": "PKPU 1",
        "year": 2026,
        "file_hash": "a" * 64,
        "namespace": "configured-namespace",
        "chunks_count": 12,
        "pasal_count": 9,
        "pinecone_confirmed": False,
    }
    with Session(get_engine()) as db:
        retry_error = IngestionErrorLog(
            workflow="WF1",
            execution_id="old-execution",
            node="Pinecone",
            message="upsert timeout",
            status="retry_requested",
            retry_attempts=1,
            retry_execution_id="workflow-exec-123",
            details="{}",
        )
        db.add(retry_error)
        db.commit()
        retry_error_id = retry_error.id
    rejected = client.post(
        "/api/v1/admin/ingestion/callback",
        json=payload,
        headers={
            "X-Ingestion-Key": "test-ingestion-key",
        },
    )
    assert rejected.status_code == 422
    payload["pinecone_confirmed"] = True
    payload["retry_error_id"] = retry_error_id
    recorded = client.post(
        "/api/v1/admin/ingestion/callback",
        json=payload,
        headers={
            "X-Ingestion-Key": "test-ingestion-key",
        },
    )
    assert recorded.status_code == 200, recorded.text
    assert client.get("/api/v1/admin/dashboard/summary").json()["indexed_chunks"] == 12
    docs = client.get("/api/v1/admin/dashboard/documents?q=PKPU&status=success")
    assert docs.status_code == 200
    assert docs.json()["items"][0]["pinecone_confirmed"] is True
    assert docs.json()["items"][0]["namespace"] == "configured-namespace"
    with Session(get_engine()) as db:
        doc = db.get(IngestionDocument, "doc-2026")
        assert doc.status == "success"
        assert doc.pinecone_confirmed is True
        assert doc.chunks_count == 12
        assert db.get(IngestionErrorLog, retry_error_id).status == "retry_succeeded"
