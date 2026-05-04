"""Real API integration tests for triage happy path behavior."""

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
from tests.conftest import FakeCreditRequestRepository


def _post_chat(client: TestClient, message: str, session_id: str | None = None):
    payload = {"message": message}
    if session_id is not None:
        payload["session_id"] = session_id
    return client.post("/api/v1/chat", json=payload)


def _repo_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "app" / "data"


def _build_app_with_controlled_classifier() -> tuple[TestClient, MockProvider]:
    repos = create_repositories(_repo_data_dir())
    provider = MockProvider(content="credit_limit")
    classifier = IntentClassifier(LLMManager(primary_provider=provider))
    deps = GraphDependencies(
        customer_repository=repos.customer_repository,
        score_limit_repository=repos.score_limit_repository,
        credit_request_repository=repos.credit_request_repository,
        exchange_provider=None,
        intent_classifier=classifier,
    )

    graph = build_graph(deps, interrupt_before=["credit_node"])
    app = create_app()
    app.dependency_overrides[get_app_graph] = lambda: graph
    return TestClient(app), provider


def _build_app_for_credit_increase_flow() -> tuple[TestClient, MockProvider]:
    repos = create_repositories(_repo_data_dir())
    provider = MockProvider(content="credit_increase")
    classifier = IntentClassifier(LLMManager(primary_provider=provider))
    deps = GraphDependencies(
        customer_repository=repos.customer_repository,
        score_limit_repository=repos.score_limit_repository,
        credit_request_repository=FakeCreditRequestRepository(),
        exchange_provider=None,
        intent_classifier=classifier,
    )

    graph = build_graph(deps)
    app = create_app()
    app.dependency_overrides[get_app_graph] = lambda: graph
    return TestClient(app), provider


def test_happy_path_auth_with_dd_dash_format() -> None:
    client = TestClient(create_app())

    turn_1 = _post_chat(client, "olá")
    assert turn_1.status_code == 200
    payload_1 = turn_1.json()
    session_id = payload_1["session_id"]
    assert payload_1["state"] == "ASKING_CPF"
    assert payload_1["ended"] is False

    turn_2 = _post_chat(client, "12345678901", session_id=session_id)
    assert turn_2.status_code == 200
    payload_2 = turn_2.json()
    assert payload_2["state"] == "ASKING_BIRTH_DATE"
    assert payload_2["ended"] is False

    turn_3 = _post_chat(client, "12-05-1990", session_id=session_id)
    assert turn_3.status_code == 200
    payload_3 = turn_3.json()
    assert payload_3["state"] in {"AUTHENTICATED", "IDENTIFYING_INTENT"}
    assert payload_3["ended"] is False
    assert payload_3["state"] != "ERROR"
    assert payload_3["state"] != "ENDED"


def test_birth_date_slash_format_is_rejected() -> None:
    client = TestClient(create_app())

    first = _post_chat(client, "olá").json()
    session_id = first["session_id"]
    _post_chat(client, "12345678901", session_id=session_id)

    third = _post_chat(client, "12/05/1990", session_id=session_id)

    assert third.status_code == 200
    payload = third.json()
    assert payload["state"] == "ASKING_BIRTH_DATE"
    assert payload["ended"] is False
    assert "dd-mm-aaaa" in payload["reply"].lower()


def test_invalid_date_does_not_end_before_third_failure() -> None:
    client = TestClient(create_app())

    first = _post_chat(client, "olá").json()
    session_id = first["session_id"]
    _post_chat(client, "12345678901", session_id=session_id)

    third = _post_chat(client, "data inválida", session_id=session_id)
    payload_3 = third.json()
    assert third.status_code == 200
    assert payload_3["state"] == "ASKING_BIRTH_DATE"
    assert payload_3["ended"] is False
    assert payload_3["state"] != "ERROR"

    fourth = _post_chat(client, "12-05-1990", session_id=session_id)
    payload_4 = fourth.json()
    assert fourth.status_code == 200
    assert payload_4["state"] in {"AUTHENTICATED", "IDENTIFYING_INTENT"}
    assert payload_4["ended"] is False


def test_three_auth_failures_end_safely() -> None:
    client = TestClient(create_app())

    first = _post_chat(client, "olá").json()
    session_id = first["session_id"]
    _post_chat(client, "12345678901", session_id=session_id)

    _post_chat(client, "01-01-1999", session_id=session_id)
    _post_chat(client, "01-01-1999", session_id=session_id)
    last = _post_chat(client, "01-01-1999", session_id=session_id)

    assert last.status_code == 200
    payload = last.json()
    assert payload["ended"] is True
    assert payload["state"] in {"ENDING", "ENDED"}
    assert "traceback" not in payload["reply"].lower()


def test_post_auth_routes_to_credit_limit() -> None:
    client, provider = _build_app_with_controlled_classifier()

    first = _post_chat(client, "olá").json()
    session_id = first["session_id"]
    _post_chat(client, "12345678901", session_id=session_id)
    _post_chat(client, "12-05-1990", session_id=session_id)

    routed = _post_chat(client, "quero consultar meu limite", session_id=session_id)

    assert routed.status_code == 200
    payload = routed.json()
    assert payload["ended"] is False
    assert payload["state"] != "ERROR"
    assert payload["state"] != "ENDED"
    assert payload["state"] != "ASKING_CPF"
    assert payload["agent"] == "credit"
    assert len(provider.requests) == 1


def test_post_auth_credit_increase_accepts_brl_amount_and_advances() -> None:
    client, provider = _build_app_for_credit_increase_flow()

    first = _post_chat(client, "olá").json()
    session_id = first["session_id"]
    _post_chat(client, "12345678901", session_id=session_id)
    _post_chat(client, "12-05-1990", session_id=session_id)

    ask_limit = _post_chat(client, "quero aumentar meu limite", session_id=session_id)
    assert ask_limit.status_code == 200
    ask_payload = ask_limit.json()
    assert ask_payload["agent"] == "credit"
    assert ask_payload["state"] == "ASKING_NEW_LIMIT"

    decision = _post_chat(client, "R$ 8.000,00", session_id=session_id)
    assert decision.status_code == 200
    decision_payload = decision.json()
    assert decision_payload["agent"] == "credit"
    assert decision_payload["state"] == "CREDIT_REQUEST_APPROVED"
    assert decision_payload["ended"] is False
    assert "aprovada" in decision_payload["reply"].lower()

    # LLM is used for intent routing, but the amount follow-up is deterministic
    # and must not trigger a second intent classification turn.
    assert len(provider.requests) == 1
