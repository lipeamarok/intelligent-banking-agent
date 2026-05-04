"""Integration tests for session reset/resume endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies as api_dependencies
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_api_caches_between_tests():
    yield
    api_dependencies.clear_api_dependency_caches()


def test_reset_session_without_id_creates_session(client: TestClient):
    response = client.post("/api/v1/sessions/reset")
    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Session reset successfully"
    assert payload["state"] == "STARTED"
    assert payload["ended"] is False
    assert payload["session_id"]


def test_reset_session_with_empty_body_creates_new_session(client: TestClient):
    """Regression: POST /sessions/reset with {} (no session_id) must return 200, not 422."""
    response = client.post("/api/v1/sessions/reset", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Session reset successfully"
    assert payload["state"] == "STARTED"
    assert payload["session_id"]


def test_get_session_by_id_returns_session(client: TestClient):
    session_id = client.post("/api/v1/sessions/reset").json()["session_id"]
    response = client.get(f"/api/v1/sessions/{session_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["state"] == "STARTED"
    assert payload["authenticated"] is False
    assert len(payload["recent_messages"]) <= 3


def test_get_missing_session_returns_controlled_error(client: TestClient):
    response = client.get("/api/v1/sessions/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "SESSION_NOT_FOUND"
    assert "Traceback" not in str(payload)


def test_recent_messages_does_not_exceed_three(client: TestClient):
    session_id = client.post("/api/v1/sessions/reset").json()["session_id"]
    for i in range(4):
        client.post("/api/v1/chat", json={"session_id": session_id, "message": f"msg-{i}"})

    payload = client.get(f"/api/v1/sessions/{session_id}").json()
    assert len(payload["recent_messages"]) <= 3


def test_session_service_is_in_memory_behavior(client: TestClient):
    first_session_id = client.post("/api/v1/sessions/reset").json()["session_id"]

    api_dependencies.clear_api_dependency_caches()

    resumed = client.get(f"/api/v1/sessions/{first_session_id}")
    assert resumed.status_code == 404
    assert resumed.json()["error"]["code"] == "SESSION_NOT_FOUND"
