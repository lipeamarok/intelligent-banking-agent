"""Integration tests for GET /api/v1/health."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check_returns_200(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_response_contains_required_fields(client: TestClient):
    data = client.get("/api/v1/health").json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp" in data
    assert "trace_id" in data
    assert data["dependencies"] == {"api": "ok"}


def test_health_trace_id_is_valid_uuid(client: TestClient):
    trace_id = client.get("/api/v1/health").json()["trace_id"]
    uuid.UUID(trace_id)
