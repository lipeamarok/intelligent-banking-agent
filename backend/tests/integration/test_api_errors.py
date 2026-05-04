"""Integration tests for error handling envelopes."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_validation_error_returns_error_envelope(client: TestClient):
    response = client.post("/api/v1/chat", json={})
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "trace_id" in payload["error"]


def test_internal_error_does_not_expose_stack_trace(client: TestClient):
    response = client.post("/api/v1/chat", json={"session_id": "missing", "message": "oi"})
    # Controlled session-not-found in this path.
    assert response.status_code == 404
    text = str(response.json())
    assert "Traceback" not in text
    assert "File \"" not in text


def test_graph_unavailable_error_does_not_expose_runtime_details(client: TestClient):
    with patch("app.api.dependencies.create_application_graph", side_effect=RuntimeError("secret bootstrap failure")):
        from app.api import dependencies as api_dependencies

        api_dependencies.clear_api_dependency_caches()
        response = client.post("/api/v1/chat", json={"message": "oi"})

    assert response.status_code == 503
    payload = response.json()
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert payload["error"]["message"] == "Service temporarily unavailable"
    assert "secret bootstrap failure" not in str(payload)


def test_graph_unavailable_logs_sanitized_reason(client: TestClient, capsys):
    with patch(
        "app.api.dependencies.create_application_graph",
        side_effect=RuntimeError("OPENAI_API_KEY=super-secret-value"),
    ):
        from app.api import dependencies as api_dependencies

        api_dependencies.clear_api_dependency_caches()
        response = client.post("/api/v1/chat", json={"message": "oi"})

    assert response.status_code == 503
    captured = capsys.readouterr()
    logs = f"{captured.out}\n{captured.err}"
    assert "Application graph unavailable" in logs
    assert "[REDACTED]" in logs
    assert "OPENAI_API_KEY=super-secret-value" not in logs
