"""Integration tests for POST /api/v1/chat endpoint."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from langgraph.errors import GraphRecursionError

from app.api import dependencies as api_dependencies
from app.api.dependencies import GraphUnavailableError, get_app_graph
from app.main import app, create_app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()
    api_dependencies.clear_api_dependency_caches()


class _FakeGraph:
    def __init__(self, state: dict):
        self._state = state

    def invoke(self, _input, config=None):
        return dict(self._state)


class _UnavailableFakeGraph:
    def invoke(self, *_args, **_kwargs):
        raise GraphUnavailableError("Application graph unavailable")


class _RuntimeBoomGraph:
    def invoke(self, *_args, **_kwargs):
        raise RuntimeError("runtime boom with internal details")


class _CheckpointSnapshot:
    def __init__(self, values: dict):
        self.values = values


class _RecursionThenCheckpointGraph:
    def invoke(self, *_args, **_kwargs):
        raise GraphRecursionError("loop waiting for user input")

    def get_state(self, *_args, **_kwargs):
        return _CheckpointSnapshot(
            {
                "current_state": "ASKING_CPF",
                "next_step": "triage_node",
                "last_assistant_output": "Por favor, informe seu CPF para continuarmos.",
                "ended": False,
            }
        )


def _write_min_csvs(base: Path) -> None:
    (base / "clientes.csv").write_text(
        "cpf,data_nascimento,nome,score_atual,limite_credito\n"
        "12345678901,1990-05-12,Ana Silva,720,5000.0\n",
        encoding="utf-8",
    )
    (base / "score_limite.csv").write_text(
        "score_minimo,score_maximo,limite_maximo_permitido\n"
        "0,299,1000.0\n300,499,2500.0\n500,699,5000.0\n700,849,10000.0\n850,1000,20000.0\n",
        encoding="utf-8",
    )
    (base / "solicitacoes_aumento_limite.csv").write_text(
        "cpf_cliente,data_hora_solicitacao,limite_atual,novo_limite_solicitado,status_pedido\n",
        encoding="utf-8",
    )


def test_chat_without_session_id_creates_session(client: TestClient):
    app.dependency_overrides[get_app_graph] = lambda: _FakeGraph(
        {
            "current_state": "ASKING_CPF",
            "last_assistant_output": "Informe seu CPF.",
            "ended": False,
        }
    )

    response = client.post("/api/v1/chat", json={"message": "oi"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"]
    assert payload["agent"] == "triage"
    assert payload["state"] == "ASKING_CPF"
    assert "metadata" in payload


def test_chat_empty_message_returns_validation_error(client: TestClient):
    response = client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422


def test_chat_response_does_not_expose_internal_state(client: TestClient):
    app.dependency_overrides[get_app_graph] = lambda: _FakeGraph(
        {
            "current_state": "ASKING_CPF",
            "last_assistant_output": "ok",
            "authenticated_cpf": "12345678901",
            "current_customer": {"cpf": "123"},
            "provider_used": "grok",
            "ended": False,
        }
    )

    payload = client.post("/api/v1/chat", json={"message": "oi"}).json()
    assert "authenticated_cpf" not in payload
    assert "current_customer" not in payload
    assert "provider_used" not in payload
    assert "graph_state" not in payload


def test_simple_three_turn_flow_with_same_session(client: TestClient):
    graph = MagicMock()
    graph.invoke.side_effect = [
        {
            "current_state": "ASKING_BIRTH_DATE",
            "last_assistant_output": "Agora sua data de nascimento.",
            "ended": False,
        },
        {
            "current_state": "AUTHENTICATED",
            "last_assistant_output": "Autenticado.",
            "ended": False,
        },
        {
            "current_state": "SHOWING_CREDIT_LIMIT",
            "last_assistant_output": "Seu limite e R$ 1.000.",
            "ended": False,
        },
    ]
    app.dependency_overrides[get_app_graph] = lambda: graph

    first = client.post("/api/v1/chat", json={"message": "123.456.789-01"}).json()
    session_id = first["session_id"]
    assert first["state"] == "ASKING_BIRTH_DATE"

    second = client.post(
        "/api/v1/chat",
        json={"session_id": session_id, "message": "12/05/1990"},
    ).json()
    assert second["state"] == "AUTHENTICATED"

    third = client.post(
        "/api/v1/chat",
        json={"session_id": session_id, "message": "consultar limite"},
    ).json()
    assert third["state"] == "SHOWING_CREDIT_LIMIT"


def test_chat_response_always_has_metadata(client: TestClient):
    app.dependency_overrides[get_app_graph] = lambda: _FakeGraph(
        {
            "current_state": "ERROR",
            "last_assistant_output": "erro",
            "recoverable_error": True,
            "retry_available": True,
            "ended": False,
        }
    )

    payload = client.post("/api/v1/chat", json={"message": "oi"}).json()
    assert payload["metadata"]["recoverable"] is True
    assert payload["metadata"]["retry_available"] is True
    assert payload["metadata"]["suggested_action"] == "retry"


def test_chat_graph_unavailable_returns_controlled_error_or_safe_error_response(client: TestClient):
    app.dependency_overrides[get_app_graph] = lambda: _UnavailableFakeGraph()

    response = client.post("/api/v1/chat", json={"message": "oi"})
    assert response.status_code == 503

    payload = response.json()
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert payload["error"]["message"] == "Service temporarily unavailable"
    assert payload["error"]["recoverable"] is True


def test_chat_error_response_does_not_expose_runtime_error_message(client: TestClient):
    app.dependency_overrides[get_app_graph] = lambda: _RuntimeBoomGraph()

    response = client.post("/api/v1/chat", json={"message": "oi"})
    assert response.status_code == 200
    payload = response.json()
    assert "runtime boom" not in str(payload).lower()
    assert "internal details" not in str(payload).lower()
    assert payload["state"] == "ERROR"


def test_chat_first_turn_greeting_returns_triage_prompt_when_graph_recursion_occurs(client: TestClient):
    app.dependency_overrides[get_app_graph] = lambda: _RecursionThenCheckpointGraph()

    response = client.post("/api/v1/chat", json={"message": "olá"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "ASKING_CPF"
    assert payload["agent"] == "triage"
    assert "cpf" in payload["reply"].lower()


def test_api_dependency_graph_cache_can_be_cleared_or_overridden(monkeypatch):
    api_dependencies.clear_api_dependency_caches()
    calls = {"count": 0}

    class _GraphFromFactory:
        pass

    def fake_create_application_graph(_settings):
        calls["count"] += 1
        return _GraphFromFactory()

    monkeypatch.setattr(api_dependencies, "create_application_graph", fake_create_application_graph)

    first = api_dependencies.get_app_graph()
    second = api_dependencies.get_app_graph()

    assert first is second
    assert calls["count"] == 1

    api_dependencies.clear_api_dependency_caches()
    third = api_dependencies.get_app_graph()

    assert third is not first
    assert calls["count"] == 2


def test_get_app_graph_returns_real_graph_when_settings_and_data_valid(tmp_path, monkeypatch):
    _write_min_csvs(tmp_path)

    dotenv = tmp_path / ".env"
    dotenv.write_text(
        f"DATA_DIR={tmp_path.as_posix()}\n"
        "XAI_API_KEY=xai-test\n"
        "OPENAI_API_KEY=openai-test\n"
        "EXCHANGE_API_KEY=exchange-test\n"
        "EXCHANGE_PROVIDER=searchapi\n",
        encoding="utf-8",
    )

    for key in ("DATA_DIR", "XAI_API_KEY", "OPENAI_API_KEY", "EXCHANGE_API_KEY", "EXCHANGE_PROVIDER"):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("BANKING_AI_AGENT_DOTENV_PATH", str(dotenv))

    api_dependencies.clear_api_dependency_caches()
    graph = api_dependencies.get_app_graph()

    assert not isinstance(graph, api_dependencies._UnavailableGraph)


def test_get_app_graph_unavailable_when_missing_key(tmp_path, monkeypatch):
    _write_min_csvs(tmp_path)

    dotenv = tmp_path / ".env"
    dotenv.write_text(
        f"DATA_DIR={tmp_path.as_posix()}\n"
        "OPENAI_API_KEY=openai-test\n"
        "EXCHANGE_API_KEY=exchange-test\n"
        "EXCHANGE_PROVIDER=searchapi\n",
        encoding="utf-8",
    )

    for key in ("DATA_DIR", "XAI_API_KEY", "OPENAI_API_KEY", "EXCHANGE_API_KEY", "EXCHANGE_PROVIDER"):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("BANKING_AI_AGENT_DOTENV_PATH", str(dotenv))

    api_dependencies.clear_api_dependency_caches()
    graph = api_dependencies.get_app_graph()

    assert isinstance(graph, api_dependencies._UnavailableGraph)


def test_create_app_clears_stale_graph_cache_after_env_ready(tmp_path, monkeypatch):
    # Step 1: cache unavailable graph using missing dotenv path.
    monkeypatch.setenv("BANKING_AI_AGENT_DOTENV_PATH", "__missing_for_stale_cache__.env")
    for key in ("DATA_DIR", "XAI_API_KEY", "OPENAI_API_KEY", "EXCHANGE_API_KEY", "EXCHANGE_PROVIDER"):
        monkeypatch.delenv(key, raising=False)

    api_dependencies.clear_api_dependency_caches()
    stale = api_dependencies.get_app_graph()
    assert isinstance(stale, api_dependencies._UnavailableGraph)

    # Step 2: provide valid dotenv and create app; cache must be refreshed.
    _write_min_csvs(tmp_path)
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        f"DATA_DIR={tmp_path.as_posix()}\n"
        "XAI_API_KEY=xai-test\n"
        "OPENAI_API_KEY=openai-test\n"
        "EXCHANGE_API_KEY=exchange-test\n"
        "EXCHANGE_PROVIDER=searchapi\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BANKING_AI_AGENT_DOTENV_PATH", str(dotenv))

    _ = create_app()
    refreshed = api_dependencies.get_app_graph()

    assert not isinstance(refreshed, api_dependencies._UnavailableGraph)
