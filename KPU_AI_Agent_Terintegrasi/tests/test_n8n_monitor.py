from app.core.config import Settings
from app.services import n8n_monitor


def test_monitor_fetches_all_workflow_pages_without_execution_payload(monkeypatch):
    settings = Settings(
        session_secret="test-secret-that-is-more-than-thirty-two-characters-long",
        app_env="test",
        n8n_api_url="http://n8n:5678",
        n8n_api_key="private-api-key",
    )
    requests = []

    class Response:
        is_redirect = False
        is_success = True
        status_code = 200

        def __init__(self, value):
            self.value = value

        def json(self):
            return self.value

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["headers"] == {"X-N8N-API-KEY": "private-api-key"}
            assert kwargs["follow_redirects"] is False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url, params):
            requests.append((url, params))
            if url.endswith("/workflows") and not params.get("cursor"):
                return Response({
                    "data": [{
                        "id": "wf-1",
                        "name": "Ingestion",
                        "active": True,
                        "updatedAt": "2026-11-18T10:00:00.000Z",
                        "tags": [{"name": "KPU"}],
                    }],
                    "nextCursor": "next-page",
                })
            if url.endswith("/workflows"):
                return Response({
                    "data": [{"id": "wf-2", "name": "Errors", "active": False}],
                    "nextCursor": None,
                })
            return Response({
                "data": [{
                    "id": "execution-1",
                    "workflowId": "wf-1",
                    "status": "success",
                    "mode": "trigger",
                    "startedAt": "2026-11-18T10:00:00.000Z",
                    "stoppedAt": "2026-11-18T10:01:00.000Z",
                    "data": {"sensitive": "never return"},
                }],
            })

    monkeypatch.setattr(n8n_monitor.httpx, "Client", Client)
    result = n8n_monitor.get_n8n_monitoring(settings)

    assert result.connected is True
    assert [workflow.id for workflow in result.workflows] == ["wf-1", "wf-2"]
    assert result.workflows[0].tags == ["KPU"]
    assert len(result.executions) == 1
    assert result.executions[0].id == "execution-1"
    assert result.executions[0].workflow_name == "Ingestion"
    assert "data" not in result.executions[0].model_dump()
    assert requests[0][1] == {"limit": 250}
    assert requests[1][1] == {"limit": 250, "cursor": "next-page"}
    assert requests[2][1] == {"limit": 100, "includeData": "false"}


def test_monitor_marks_missing_configuration_without_calling_n8n(monkeypatch):
    settings = Settings(
        session_secret="test-secret-that-is-more-than-thirty-two-characters-long",
        app_env="test",
    )

    def unexpected_client(**_kwargs):
        raise AssertionError("Should not connect when configuration is absent")

    monkeypatch.setattr(n8n_monitor.httpx, "Client", unexpected_client)
    result = n8n_monitor.get_n8n_monitoring(settings)
    assert result.configured is False
    assert result.connected is False
    assert result.workflows == []


def test_workflow_monitor_endpoint_requires_admin(client):
    assert client.get("/api/v1/admin/dashboard/workflows").status_code == 401
