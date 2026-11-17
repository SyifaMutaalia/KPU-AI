import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_insecure_config():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", session_secret="replace-me-with-a-really-long-string", cookie_secure=False)


def test_strong_secret_required():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, session_secret="short")
