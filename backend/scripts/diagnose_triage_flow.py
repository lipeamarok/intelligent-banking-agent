"""Diagnose triage turn contract and state evolution with real graph and CSV data."""

from __future__ import annotations

from app.bootstrap.graph import create_application_graph
from app.config.settings import load_settings_from_env


def _cfg(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def _print_state(label: str, state: dict) -> None:
    print(label)
    print(f"  current_state={state.get('current_state')}")
    print(f"  next_step={state.get('next_step')}")
    print(f"  authenticated={state.get('authenticated')}")
    print(f"  auth_attempts={state.get('auth_attempts')}")
    print(f"  ended={state.get('ended')}")
    print(f"  last_action_summary={state.get('last_action_summary')}")
    print(f"  last_assistant_output={state.get('last_assistant_output')}")


def main() -> int:
    settings = load_settings_from_env()
    graph = create_application_graph(settings=settings)
    config = _cfg("diagnose-triage-flow")

    state = {
        "session_id": "diagnose-triage-flow",
        "trace_id": "diagnose-triage-flow-trace",
        "last_user_input": "olá",
    }
    state = dict(graph.invoke(state, config=config))
    _print_state("turn_1", state)

    state["last_user_input"] = "12345678901"
    state["cpf_candidate"] = "12345678901"
    state = dict(graph.invoke(state, config=config))
    _print_state("turn_2", state)

    state["last_user_input"] = "1990-05-12"
    state["birth_date_candidate"] = "1990-05-12"
    state = dict(graph.invoke(state, config=config))
    _print_state("turn_3", state)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
