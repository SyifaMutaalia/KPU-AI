"""ASGI entry point: uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.routes import admin, chat, conversations, eppid, session
from app.core.config import get_settings
from app.db.models import Base
from app.db.session import get_engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # SQLite is the only database initialized automatically for local onboarding.
    # PostgreSQL schemas and existing tables must be managed by Alembic migrations.
    if get_settings().database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=get_engine())
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version="0.1.0",
        docs_url="/docs" if s.app_env != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if s.app_env != "production" else None,
        lifespan=lifespan,
    )
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token"])

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok", "environment": s.app_env}

    for router in (session.router, chat.router, conversations.router, eppid.router, admin.router):
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
