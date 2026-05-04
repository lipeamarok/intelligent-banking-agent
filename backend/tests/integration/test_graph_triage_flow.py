"""Real integration tests for triage flow directly on LangGraph."""

from __future__ import annotations

from app.bootstrap.graph import create_application_graph
from app.config.settings import load_settings_from_env


def _cfg(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def test_graph_first_turn_returns_asking_cpf_without_recursion_error() -> None:
    graph = create_application_graph(settings=load_settings_from_env())

    result = graph.invoke(
        {
            "session_id": "triage-graph-1",
            "trace_id": "triage-graph-1-trace",
            "last_user_input": "olá",
        },
        config=_cfg("triage-graph-1"),
    )

    state = dict(result)
    assert state["current_state"] == "ASKING_CPF"
    assert "cpf" in state.get("last_assistant_output", "").lower()


def test_graph_triage_progression_to_authenticated() -> None:
    graph = create_application_graph(settings=load_settings_from_env())
    config = _cfg("triage-graph-2")

    state = {
        "session_id": "triage-graph-2",
        "trace_id": "triage-graph-2-trace",
        "last_user_input": "olá",
    }
    first = dict(graph.invoke(state, config=config))
    assert first["current_state"] == "ASKING_CPF"

    second_input = dict(first)
    second_input["last_user_input"] = "12345678901"
    second_input["cpf_candidate"] = "12345678901"
    second = dict(graph.invoke(second_input, config=config))
    assert second["current_state"] == "ASKING_BIRTH_DATE"

    third_input = dict(second)
    third_input["last_user_input"] = "1990-05-12"
    third_input["birth_date_candidate"] = "1990-05-12"
    third = dict(graph.invoke(third_input, config=config))
    assert third["current_state"] == "AUTHENTICATED"
    assert third.get("authenticated") is True
    assert third.get("ended") is False


def test_graph_blocks_after_three_failed_auth_attempts() -> None:
    graph = create_application_graph(settings=load_settings_from_env())
    config = _cfg("triage-graph-3")

    state = {
        "session_id": "triage-graph-3",
        "trace_id": "triage-graph-3-trace",
        "last_user_input": "olá",
    }
    state = dict(graph.invoke(state, config=config))

    state["last_user_input"] = "12345678901"
    state["cpf_candidate"] = "12345678901"
    state = dict(graph.invoke(state, config=config))

    for _ in range(3):
        state["last_user_input"] = "1999-01-01"
        state["birth_date_candidate"] = "1999-01-01"
        state = dict(graph.invoke(state, config=config))

    assert state.get("ended") is True
    assert state.get("current_state") in {"ENDED", "ENDING"}
