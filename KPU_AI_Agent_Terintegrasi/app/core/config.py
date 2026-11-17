from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    rag_enabled: bool = False
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "KPU Subang AI Agent Backend"
    session_secret: str = Field(min_length=32)
    database_url: str = "sqlite:///./data/kpu_agent.db"
    cors_origins: list[str] = ["http://localhost:3000"]
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_ttl_days: int = Field(default=14, ge=1, le=90)
    chat_rate_limit_per_minute: int = Field(default=12, ge=1, le=120)
    max_context_messages: int = Field(default=12, ge=2, le=30)

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    pinecone_api_key: str = ""
    pinecone_index_name: str = ""
    pinecone_namespace: str = "kpu-subang"
    rag_top_k: int = Field(default=5, ge=1, le=10)
    rag_min_score: float = Field(default=0.55, ge=0.0, le=1.0)
    rag_allowed_hosts: list[str] = ["kab-subang.kpu.go.id", "jdih.kpu.go.id", "www.kpu.go.id", "peraturan.bpk.go.id", "peraturan.go.id"]
    kpu_website_url: str = "https://kab-subang.kpu.go.id/"
    jdih_url: str = "https://jdih.kpu.go.id/"
    eppid_url: str = "https://subangkabppid.kpu.go.id/"

    @field_validator("cors_origins", "rag_allowed_hosts")
    @classmethod
    def must_have_values(cls, value: list[str]) -> list[str]:
        if not value or any(not x.strip() for x in value):
            raise ValueError("The list must not be empty")
        return value

    @model_validator(mode="after")
    def validate_production(self):
        if self.app_env == "production":
            if self.session_secret.startswith("replace-") or self.session_secret.startswith("test-"):
                raise ValueError("Production SESSION_SECRET must be cryptographically random")
            if not self.cookie_secure:
                raise ValueError("Production requires COOKIE_SECURE=true")
            if self.cookie_samesite == "none" and not self.cookie_secure:
                raise ValueError("SameSite=None requires HTTPS")
            if any("localhost" in origin or "127.0.0.1" in origin for origin in self.cors_origins):
                raise ValueError("Production CORS_ORIGINS cannot contain localhost")
            if self.database_url.startswith("sqlite"):
                raise ValueError("Production needs a persistent PostgreSQL DATABASE_URL")
            if not (self.openai_api_key and self.pinecone_api_key and self.pinecone_index_name):
                raise ValueError("Production requires OpenAI & Pinecone credentials")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
