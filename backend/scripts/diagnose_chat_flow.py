"""Diagnose first-turn chat flow safely without exposing secrets."""

from __future__ import annotations

import os
import sys
import traceback

from langgraph.errors import GraphRecursionError

from app.api import dependencies as api_dependencies
from app.bootstrap.graph import create_application_graph
from app.config.settings import load_settings_from_env
from app.observability.logger import sanitize_text


def _print_state(label: str, state: dict) -> None:
    print(label)
    print(f"  session_id={state.get('session_id')}")
    print(f"  trace_id={state.get('trace_id')}")
    print(f"  current_state={state.get('current_state')}")
    print(f"  next_step={state.get('next_step')}")
    print(f"  ended={state.get('ended')}")
    print(f"  last_user_input={state.get('last_user_input')}")
    print(f"  last_assistant_output={state.get('last_assistant_output')}")


def main() -> int:
    settings = load_settings_from_env()
    graph = create_application_graph(settings=settings)

    session_id = "diagnose-chat-flow"
    trace_id = "diagnose-chat-flow-trace"
    config = {"configurable": {"thread_id": session_id}}
    initial_state = {
        "session_id": session_id,
        "trace_id": trace_id,
        "last_user_input": "olá",
    }

    print(f"pid: {os.getpid()}")
    print(f"python: {sys.executable}")
    print(f"cwd: {os.getcwd()}")
    print(f"data_dir_setting: {settings.data_dir}")
    _print_state("input_state:", initial_state)

    try:
        output = graph.invoke(initial_state, config=config)
        if not isinstance(output, dict):
            output = dict(output)
        _print_state("graph_output:", output)
    except GraphRecursionError as exc:
        print(f"invoke_exception_type: {type(exc).__name__}")
        print(f"invoke_exception_reason: {sanitize_text(str(exc))}")
        print(f"invoke_exception_traceback: {sanitize_text(traceback.format_exc(limit=6))}")

        try:
            snapshot = graph.get_state(config)
            values = getattr(snapshot, "values", {})
            recovered = dict(values) if isinstance(values, dict) else dict(values)
            _print_state("checkpoint_recovered_state:", recovered)
        except Exception as recover_exc:
            print(f"checkpoint_recover_failed: {type(recover_exc).__name__}: {sanitize_text(str(recover_exc))}")
            return 1
    except Exception as exc:
        print(f"invoke_exception_type: {type(exc).__name__}")
        print(f"invoke_exception_reason: {sanitize_text(str(exc))}")
        print(f"invoke_exception_traceback: {sanitize_text(traceback.format_exc(limit=6))}")
        return 1

    api_dependencies.clear_api_dependency_caches()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
