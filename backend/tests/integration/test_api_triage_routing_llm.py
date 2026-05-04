"""API integration tests for triage routing with controlled LLM behavior."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api.dependencies import get_app_graph
from app.bootstrap.dependencies import create_repositories
from app.graph.dependencies import GraphDependencies
from app.graph.graph_builder import build_graph
from app.llm.intent_classifier import IntentClassifier
from app.llm.manager import LLMManager
from app.llm.mock_provider import MockProvider
from app.main import create_app


def _repo_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "app" / "data"


def _build_app_with_controlled_classifier(
    provider_content: str,
    *,
    interrupt_before: list[str] | None = None,
) -> tuple[TestClient, MockProvider]:
    repos = create_repositories(_repo_data_dir())
    provider = MockProvider(content=provider_content)
    classifier = IntentClassifier(LLMManager(primary_provider=provider))

    deps = GraphDependencies(
        customer_repository=repos.customer_repository,
        score_limit_repository=repos.score_limit_repository,
        credit_request_repository=repos.credit_request_repository,
        exchange_provider=None,
        intent_classifier=classifier,
    )

    graph = build_graph(deps, interrupt_before=interrupt_before)
    app = create_app()
    app.dependency_overrides[get_app_graph] = lambda: graph
    return TestClient(app), provider


def _post_chat(client: TestClient, message: str, session_id: str | None = None):
    payload = {"message": message}
    if session_id is not None:
        payload["session_id"] = session_id
    return client.post("/api/v1/chat", json=payload)


def _authenticate_session(client: TestClient) -> str:
    first = _post_chat(client, "olá").json()
    session_id = first["session_id"]

    cpf_step = _post_chat(client, "12345678901", session_id=session_id)
    assert cpf_step.status_code == 200
    assert cpf_step.json()["state"] == "ASKING_BIRTH_DATE"

    auth_step = _post_chat(client, "12-05-1990", session_id=session_id)
    assert auth_step.status_code == 200
    assert auth_step.json()["state"] in {"AUTHENTICATED", "IDENTIFYING_INTENT"}
    return session_id


def test_api_does_not_route_with_llm_before_authentication() -> None:
    client, provider = _build_app_with_controlled_classifier("credit_limit")

    response = _post_chat(client, "quero consultar meu limite")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "ASKING_CPF"
    assert payload["agent"] == "triage"
    assert len(provider.requests) == 0


def test_api_routes_to_credit_after_authentication() -> None:
    client, provider = _build_app_with_controlled_classifier(
        "credit_limit",
        interrupt_before=["credit_node"],
    )
    session_id = _authenticate_session(client)

    routed = _post_chat(client, "quero consultar meu limite", session_id=session_id)

    assert routed.status_code == 200
    payload = routed.json()
    assert payload["state"] == "IDENTIFYING_INTENT"
    assert payload["agent"] == "credit"
    assert len(provider.requests) == 1


def test_api_routes_to_credit_increase_after_authentication() -> None:
    client, provider = _build_app_with_controlled_classifier(
        "credit_increase",
        interrupt_before=["credit_node"],
    )
    session_id = _authenticate_session(client)

    routed = _post_chat(client, "quero aumentar meu limite", session_id=session_id)

    assert routed.status_code == 200
    payload = routed.json()
    assert payload["state"] == "IDENTIFYING_INTENT"
    assert payload["agent"] == "credit"
    assert len(provider.requests) == 1


def test_api_routes_to_exchange_after_authentication() -> None:
    client, provider = _build_app_with_controlled_classifier(
        "exchange_quote",
        interrupt_before=["exchange_node"],
    )
    session_id = _authenticate_session(client)

    routed = _post_chat(client, "quero cotação de câmbio", session_id=session_id)

    assert routed.status_code == 200
    payload = routed.json()
    assert payload["state"] == "IDENTIFYING_INTENT"
    assert payload["agent"] == "exchange"
    assert len(provider.requests) == 1


def test_api_invalid_llm_output_falls_back_to_unknown_intent() -> None:
    client, provider = _build_app_with_controlled_classifier("output not allowed")
    session_id = _authenticate_session(client)

    routed = _post_chat(client, "quero consultar limite", session_id=session_id)

    assert routed.status_code == 200
    payload = routed.json()
    assert payload["state"] == "ENDED"
    assert payload["agent"] == "triage"
    assert payload["ended"] is True
    assert len(provider.requests) == 3


def test_api_rejects_raw_node_name_output_from_llm() -> None:
    client, provider = _build_app_with_controlled_classifier("credit_node")
    session_id = _authenticate_session(client)

    routed = _post_chat(client, "quero limite", session_id=session_id)

    assert routed.status_code == 200
    payload = routed.json()
    assert payload["state"] == "ENDED"
    assert payload["agent"] == "triage"
    assert payload["ended"] is True
    assert len(provider.requests) == 3
