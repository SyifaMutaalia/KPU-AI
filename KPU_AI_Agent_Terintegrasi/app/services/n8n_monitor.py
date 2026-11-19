"""Read-only, bounded access to the configured n8n public API."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.config import Settings, get_settings
from app.schemas.admin import (
    AdminN8nExecutionOut,
    AdminN8nMonitorOut,
    AdminN8nWorkflowOut,
)

logger = logging.getLogger(__name__)
_PAGE_SIZE = 250
_MAX_PAGES = 20
_EXECUTION_LIMIT = 100
_REQUEST_BUDGET_SECONDS = 50


class N8nMonitorError(RuntimeError):
    pass


def _api_base(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise N8nMonitorError("N8N_API_URL harus berupa URL HTTP(S) tanpa kredensial.")
    return url.rstrip("/") + "/"


def _request_page(
    client: httpx.Client, endpoint: str, params: dict[str, str | int]
) -> dict:
    response = client.get(endpoint, params=params)
    if response.is_redirect:
        raise N8nMonitorError("n8n API mengirim redirect yang tidak diizinkan.")
    if not response.is_success:
        logger.warning("n8n monitoring API returned HTTP %s", response.status_code)
        raise N8nMonitorError("n8n API menolak atau gagal memproses permintaan.")
    try:
        payload = response.json()
    except ValueError as exc:
        raise N8nMonitorError("n8n API mengembalikan JSON yang tidak valid.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise N8nMonitorError("Format respons n8n API tidak dikenali.")
    return payload


def _fetch_workflows(
    client: httpx.Client, endpoint: str, deadline: float
) -> list[AdminN8nWorkflowOut]:
    records: list[AdminN8nWorkflowOut] = []
    seen_cursors: set[str] = set()
    cursor: str | None = None
    for page_number in range(_MAX_PAGES):
        if time.monotonic() >= deadline:
            raise N8nMonitorError("Pemindaian workflow n8n melewati batas waktu aman.")
        params: dict[str, str | int] = {"limit": _PAGE_SIZE}
        if cursor:
            params["cursor"] = cursor
        payload = _request_page(client, endpoint, params)
        for item in payload["data"]:
            if not isinstance(item, dict):
                raise N8nMonitorError("n8n API mengembalikan workflow yang tidak valid.")
            tags = item.get("tags") or []
            if not isinstance(tags, list):
                tags = []
            updated = item.get("updatedAt")
            records.append(
                AdminN8nWorkflowOut(
                    id=str(item.get("id", "")),
                    name=str(item.get("name", "")),
                    active=item.get("active") is True,
                    updated_at=_parse_datetime(updated),
                    tags=[
                        str(tag["name"])
                        for tag in tags
                        if isinstance(tag, dict) and tag.get("name")
                    ],
                )
            )
        next_cursor = payload.get("nextCursor")
        if not next_cursor:
            return records
        cursor = str(next_cursor)
        if cursor in seen_cursors:
            raise N8nMonitorError("n8n API mengembalikan pagination cursor berulang.")
        seen_cursors.add(cursor)
        if page_number == _MAX_PAGES - 1:
            raise N8nMonitorError("Daftar workflow n8n melebihi batas pagination aman.")
    return records


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def get_n8n_monitoring(settings: Settings | None = None) -> AdminN8nMonitorOut:
    settings = settings or get_settings()
    if not settings.n8n_api_url or not settings.n8n_api_key:
        return AdminN8nMonitorOut(
            configured=False,
            connected=False,
            message="N8N_API_URL dan N8N_API_KEY belum dikonfigurasi di backend.",
            workflows=[],
            executions=[],
        )

    try:
        base = _api_base(settings.n8n_api_url)
        workflows_url = urljoin(base, "api/v1/workflows")
        executions_url = urljoin(base, "api/v1/executions")
        with httpx.Client(
            timeout=httpx.Timeout(8.0),
            follow_redirects=False,
            headers={"X-N8N-API-KEY": settings.n8n_api_key},
        ) as client:
            deadline = time.monotonic() + _REQUEST_BUDGET_SECONDS
            workflows = _fetch_workflows(client, workflows_url, deadline)
            if time.monotonic() >= deadline:
                raise N8nMonitorError("Monitoring n8n melewati batas waktu aman.")
            executions_response = _request_page(
                client,
                executions_url,
                {"limit": _EXECUTION_LIMIT, "includeData": "false"},
            )
    except (httpx.HTTPError, N8nMonitorError, ValueError) as exc:
        logger.warning("n8n monitoring unavailable (%s)", type(exc).__name__)
        raise N8nMonitorError(
            "Tidak dapat memuat monitoring n8n. Periksa koneksi dan konfigurasi API."
        ) from None

    execution_records: list[AdminN8nExecutionOut] = []
    workflow_names = {workflow.id: workflow.name for workflow in workflows}
    for item in executions_response["data"]:
        if not isinstance(item, dict):
            raise N8nMonitorError("n8n API mengembalikan execution yang tidak valid.")
        workflow = item.get("workflow") or {}
        if not isinstance(workflow, dict):
            workflow = {}
        workflow_id = str(item.get("workflowId") or workflow.get("id") or "")
        execution_records.append(
            AdminN8nExecutionOut(
                id=str(item.get("id", "")),
                workflow_id=workflow_id,
                workflow_name=str(
                    item.get("workflowName")
                    or workflow.get("name")
                    or workflow_names.get(workflow_id)
                    or "Workflow"
                ),
                status=str(item.get("status") or "unknown"),
                mode=str(item["mode"]) if item.get("mode") is not None else None,
                started_at=_parse_datetime(
                    item.get("startedAt") or item.get("started_at")
                ),
                stopped_at=_parse_datetime(
                    item.get("stoppedAt") or item.get("stopped_at")
                ),
            )
        )
    return AdminN8nMonitorOut(
        configured=True,
        connected=True,
        message="Terhubung ke n8n. Data workflow dan eksekusi dibaca langsung dari API.",
        workflows=workflows,
        executions=execution_records,
    )
