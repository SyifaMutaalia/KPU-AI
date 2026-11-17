import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-that-is-more-than-thirty-two-characters-long")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    monkeypatch.setenv("COOKIE_SECURE", "false")
    from app.core.config import get_settings
    from app.db.session import get_engine
    get_settings.cache_clear()
    get_engine.cache_clear()
    from app.main import create_app
    with TestClient(create_app()) as test_client:
        yield test_client
    get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()
