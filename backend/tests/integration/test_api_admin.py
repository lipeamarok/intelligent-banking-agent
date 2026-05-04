"""Integration tests for admin CSV endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies as api_dependencies
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_caches():
    yield
    api_dependencies.clear_api_dependency_caches()


class TestAdminCsvRead:
    def test_get_clientes_returns_200(self, client: TestClient):
        response = client.get("/api/v1/admin/csv/clientes")
        assert response.status_code == 200
        payload = response.json()
        assert payload["table"] == "clientes"
        assert "cpf" in payload["columns"]
        assert isinstance(payload["rows"], list)
        assert len(payload["rows"]) >= 1

    def test_get_score_limite_returns_200(self, client: TestClient):
        response = client.get("/api/v1/admin/csv/score_limite")
        assert response.status_code == 200
        payload = response.json()
        assert payload["table"] == "score_limite"
        assert "score_minimo" in payload["columns"]

    def test_get_solicitacoes_returns_200(self, client: TestClient):
        response = client.get("/api/v1/admin/csv/solicitacoes")
        assert response.status_code == 200
        payload = response.json()
        assert payload["table"] == "solicitacoes"

    def test_unknown_table_returns_422(self, client: TestClient):
        response = client.get("/api/v1/admin/csv/unknown_table")
        assert response.status_code == 422

    def test_path_traversal_rejected(self, client: TestClient):
        """Enum validation prevents directory traversal via table param."""
        response = client.get("/api/v1/admin/csv/../../etc/passwd")
        assert response.status_code in {422, 404}


class TestAdminCsvReset:
    def test_reset_returns_200_and_table_list(self, client: TestClient):
        response = client.post("/api/v1/admin/csv/reset")
        assert response.status_code == 200
        payload = response.json()
        assert payload["reset"] is True
        assert isinstance(payload["tables"], list)
        assert len(payload["tables"]) == 3

    def test_reset_restores_default_row_count(self, client: TestClient):
        # Verify clientes has exactly 3 seed rows after reset.
        client.post("/api/v1/admin/csv/reset")
        response = client.get("/api/v1/admin/csv/clientes")
        assert response.status_code == 200
        assert len(response.json()["rows"]) == 3
