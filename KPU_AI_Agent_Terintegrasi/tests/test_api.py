from app.schemas.chat import Source
from app.services.ai_service import AgentResult


def fake_answer(message, history):
    return AgentResult(answer="Silakan periksa dokumen resmi.", sources=[Source(
        title="Dokumen KPU", url="https://jdih.kpu.go.id/"
    )], grounded=True)


def auth(client):
    response = client.get("/api/v1/session")
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_csrf_and_session(client, monkeypatch):
    monkeypatch.setattr("app.services.ai_service.answer_question", fake_answer)
    assert client.post("/api/v1/chat", json={"message": "Halo"}).status_code == 403
    headers = auth(client)
    assert client.post("/api/v1/chat", json={"message": "Halo"}, headers=headers).status_code == 200
    assert client.post("/api/v1/chat", json={"message": "Halo"}, headers={**headers, "Origin": "https://attacker.test"}).status_code == 403


def test_chat_history_isolation_and_delete(client, monkeypatch):
    monkeypatch.setattr("app.services.ai_service.answer_question", fake_answer)
    headers = auth(client)
    reply = client.post("/api/v1/chat", json={"message": "Cara mencari regulasi?"}, headers=headers)
    assert reply.status_code == 200, reply.text
    cid = reply.json()["conversation_id"]
    assert reply.json()["grounded"] is True
    assert len(client.get(f"/api/v1/conversations/{cid}").json()["messages"]) == 2
    assert len(client.get("/api/v1/conversations").json()) == 1

    from fastapi.testclient import TestClient
    with TestClient(client.app) as other:
        assert other.get(f"/api/v1/conversations/{cid}").status_code == 404
        assert other.get("/api/v1/conversations").json() == []
        other_headers = auth(other)
        assert other.delete(f"/api/v1/conversations/{cid}", headers=other_headers).status_code == 404
    assert client.delete(f"/api/v1/conversations/{cid}", headers=headers).status_code == 204
    assert client.get("/api/v1/conversations").json() == []


def test_pii_rejected(client, monkeypatch):
    monkeypatch.setattr("app.services.ai_service.answer_question", fake_answer)
    headers = auth(client)
    response = client.post("/api/v1/chat", json={"message": "Email saya contoh@domain.com"}, headers=headers)
    assert response.status_code == 422
    assert client.get("/api/v1/conversations").json() == []


def test_draft_api(client, monkeypatch):
    from app.schemas.eppid import DraftOut
    monkeypatch.setattr("app.services.draft_service.generate_draft", lambda p: DraftOut(
        informasi_yang_dimohon=p.information_needed, tujuan_penggunaan_informasi=p.purpose,
        official_url="https://subangkabppid.kpu.go.id/", note="Hanya draf"
    ))
    headers = auth(client)
    payload = {"information_needed": "Rekapitulasi hasil Pemilu 2024 Kabupaten Subang", "purpose": "Penelitian akademik"}
    r = client.post("/api/v1/eppid/draft", json=payload, headers=headers)
    assert r.status_code == 200
    assert r.json()["tujuan_penggunaan_informasi"] == "Penelitian akademik"


def test_chat_rate_limit(client, monkeypatch):
    monkeypatch.setattr("app.services.ai_service.answer_question", fake_answer)
    monkeypatch.setenv("CHAT_RATE_LIMIT_PER_MINUTE", "1")
    from app.core.config import get_settings
    get_settings.cache_clear()
    headers = auth(client)
    payload = {"message": "Bagaimana cara mencari keputusan KPU?"}
    assert client.post("/api/v1/chat", json=payload, headers=headers).status_code == 200
    assert client.post("/api/v1/chat", json=payload, headers=headers).status_code == 429
