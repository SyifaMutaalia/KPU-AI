from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AdminLoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if (
            "@" not in normalized
            or normalized.startswith("@")
            or normalized.endswith("@")
        ):
            raise ValueError("Format email tidak valid.")
        return normalized


class AdminPasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=12, max_length=128)


class ForgotPasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ResetPasswordIn(AdminPasswordIn):
    token: str = Field(min_length=32, max_length=256)


class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class AdminUserOut(BaseModel):
    id: str
    email: str
    must_change_password: bool


class AdminLoginOut(BaseModel):
    csrf_token: str
    user: AdminUserOut


class AdminCsrfOut(BaseModel):
    csrf_token: str


class AdminMessageOut(BaseModel):
    message: str


class AdminSummaryOut(BaseModel):
    documents: dict[str, int]
    indexed_chunks: int | None
    indexed_pasal: int | None
    last_sync: datetime | None
    workflows: dict[str, dict[str, str | datetime | None]]
    activities: list[dict[str, str | datetime | None]]


class AdminN8nWorkflowOut(BaseModel):
    id: str
    name: str
    active: bool
    updated_at: datetime | None
    tags: list[str]


class AdminN8nExecutionOut(BaseModel):
    id: str
    workflow_id: str
    workflow_name: str
    status: str
    mode: str | None
    started_at: datetime | None
    stopped_at: datetime | None


class AdminN8nMonitorOut(BaseModel):
    configured: bool
    connected: bool
    message: str
    workflows: list[AdminN8nWorkflowOut]
    executions: list[AdminN8nExecutionOut]


class AdminDocumentOut(BaseModel):
    id: str
    source_url: str
    document_type: str | None
    document_number: str | None
    title: str | None
    year: int | None
    file_hash: str | None
    status: str
    namespace: str | None
    last_processed_at: datetime | None
    chunks_count: int | None
    pasal_count: int | None
    pinecone_confirmed: bool


class AdminDocumentsOut(BaseModel):
    items: list[AdminDocumentOut]
    page: int
    page_size: int
    total: int


class AdminErrorOut(BaseModel):
    id: str
    occurred_at: datetime
    workflow: str
    execution_id: str
    node: str
    message: str
    status: str
    details: str
    retry_attempts: int


class AdminErrorsOut(BaseModel):
    items: list[AdminErrorOut]
    page: int
    page_size: int
    total: int


class RetryOut(BaseModel):
    status: Literal["accepted", "pending_confirmation"]
    message: str
    n8n_execution_id: str | None


class IngestionCallbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow: str = Field(min_length=1, max_length=120)
    execution_id: str = Field(min_length=1, max_length=128)
    retry_error_id: str | None = Field(default=None, max_length=36)
    status: Literal["processing", "success", "failed"]
    document_id: str = Field(min_length=1, max_length=128)
    source_url: str = Field(min_length=1, max_length=2048)
    document_type: str | None = Field(default=None, max_length=120)
    document_number: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=2000)
    year: int | None = Field(default=None, ge=1800, le=2200)
    file_hash: str | None = Field(default=None, max_length=128)
    namespace: str | None = Field(default=None, max_length=255)
    chunks_count: int | None = Field(default=None, ge=0)
    pasal_count: int | None = Field(default=None, ge=0)
    pinecone_confirmed: bool = False


class IngestionCallbackOut(BaseModel):
    status: str
    document_id: str
    run_id: str
