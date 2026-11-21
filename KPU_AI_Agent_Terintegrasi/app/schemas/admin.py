from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    """Reset dengan tautan email (token) ATAU dengan email + kode verifikasi 6 digit."""

    token: str | None = Field(default=None, min_length=32, max_length=256)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    code: str | None = Field(default=None, pattern=r"^\d{6}$")

    @field_validator("email")
    @classmethod
    def normalize_reset_email(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else value

    @model_validator(mode="after")
    def token_or_code(self):
        if not self.token and not (self.email and self.code):
            raise ValueError("Isi tautan reset, atau email beserta kode verifikasi 6 digit.")
        return self


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
    open_errors: int = 0
    latest_error_at: datetime | None = None


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


class IngestionErrorCallbackIn(BaseModel):
    """Error yang dikirim WF2 (n8n Error Trigger) ke backend."""

    model_config = ConfigDict(extra="forbid")
    workflow: str = Field(min_length=1, max_length=120)
    workflow_id: str | None = Field(default=None, max_length=128)
    execution_id: str = Field(min_length=1, max_length=128)
    node: str | None = Field(default=None, max_length=255)
    message: str = Field(min_length=1, max_length=20000)
    stack: str | None = Field(default=None, max_length=20000)
    mode: str | None = Field(default=None, max_length=64)
    retry_of: str | None = Field(default=None, max_length=128)
    execution_url: str | None = Field(default=None, max_length=2048)


class IngestionErrorCallbackOut(BaseModel):
    error_id: str
    status: str
    created: bool
    retry_marked_failed: int


class IngestionRunIn(BaseModel):
    """Permintaan admin menjalankan WF1: tanpa pdf_url = pindai JDIH, dengan pdf_url = satu PDF."""

    model_config = ConfigDict(extra="forbid")
    pdf_url: str | None = Field(default=None, max_length=2048)
    title: str | None = Field(default=None, max_length=500)


class IngestionRunOut(BaseModel):
    status: Literal["accepted"]
    message: str
    n8n_execution_id: str
