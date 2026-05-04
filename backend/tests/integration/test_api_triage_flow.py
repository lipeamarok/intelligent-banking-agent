"""Real integration tests for triage flow via API, graph and CSV repositories."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import create_app


def _post_chat(client: TestClient, message: str, session_id: str | None = None):
    payload = {"message": message}
    if session_id is not None:
        payload["session_id"] = session_id
    return client.post("/api/v1/chat", json=payload)


def test_first_turn_requests_cpf() -> None:
    client = TestClient(create_app())

    response = _post_chat(client, "olá")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "ASKING_CPF"
    assert payload["agent"] == "triage"
    assert payload["ended"] is False
    assert "cpf" in payload["reply"].lower()
    assert "current_customer" not in payload
    assert "authenticated_cpf" not in payload


def test_valid_cpf_requests_birth_date() -> None:
    client = TestClient(create_app())

    first = _post_chat(client, "olá").json()
    session_id = first["session_id"]

    second = _post_chat(client, "12345678901", session_id=session_id)

    assert second.status_code == 200
    payload = second.json()
    assert payload["session_id"] == session_id
    assert payload["state"] == "ASKING_BIRTH_DATE"
    assert payload["ended"] is False
    assert "nascimento" in payload["reply"].lower()


def test_valid_birth_date_authenticates_without_exposing_internal_customer() -> None:
    client = TestClient(create_app())

    first = _post_chat(client, "olá").json()
    session_id = first["session_id"]
    _post_chat(client, "12345678901", session_id=session_id)

    third = _post_chat(client, "12-05-1990", session_id=session_id)

    assert third.status_code == 200
    payload = third.json()
    assert payload["session_id"] == session_id
    assert payload["state"] in {"AUTHENTICATED", "IDENTIFYING_INTENT"}
    assert payload["ended"] is False
    assert "current_customer" not in payload
    assert "authenticated_cpf" not in payload

    resumed = client.get(f"/api/v1/sessions/{session_id}")
    assert resumed.status_code == 200
    resumed_payload = resumed.json()
    assert resumed_payload["authenticated"] is True
    assert resumed_payload["state"] in {"AUTHENTICATED", "IDENTIFYING_INTENT"}


def test_unknown_cpf_returns_safe_retry_path() -> None:
    client = TestClient(create_app())

    first = _post_chat(client, "olá").json()
    session_id = first["session_id"]
    second = _post_chat(client, "00000000000", session_id=session_id)

    assert second.status_code == 200
    payload = second.json()
    assert payload["state"] == "ASKING_CPF"
    assert payload["ended"] is False
    assert "não consegui localizar o cpf" in payload["reply"].lower()
    assert "traceback" not in str(payload).lower()


def test_wrong_birth_date_keeps_authentication_flow_open() -> None:
    client = TestClient(create_app())

    first = _post_chat(client, "olá").json()
    session_id = first["session_id"]
    _post_chat(client, "12345678901", session_id=session_id)

    third = _post_chat(client, "01-01-1999", session_id=session_id)

    assert third.status_code == 200
    payload = third.json()
    assert payload["state"] == "ASKING_BIRTH_DATE"
    assert payload["ended"] is False


def test_blocks_session_after_three_auth_failures() -> None:
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
    assert payload["state"] in {"ENDING", "ENDED", "ERROR"}


def test_session_id_persists_and_state_evolves() -> None:
    client = TestClient(create_app())

    first = _post_chat(client, "olá")
    payload1 = first.json()
    session_id = payload1["session_id"]

    second = _post_chat(client, "12345678901", session_id=session_id)
    payload2 = second.json()

    assert payload2["session_id"] == session_id
    assert payload1["state"] == "ASKING_CPF"
    assert payload2["state"] == "ASKING_BIRTH_DATE"


def test_first_turn_does_not_fallback_to_generic_error_response() -> None:
    client = TestClient(create_app())

    response = _post_chat(client, f"olá {uuid.uuid4()}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "ASKING_CPF"
    assert payload["agent"] == "triage"
    assert "não consegui processar" not in payload["reply"].lower()
