"""Diagnose the real triage happy path via API TestClient."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.dependencies import get_app_graph
from app.bootstrap.dependencies import create_repositories
from app.graph.dependencies import GraphDependencies
from app.graph.graph_builder import build_graph
from app.llm.intent_classifier import IntentClassifier
from app.llm.manager import LLMManager
from app.llm.mock_provider import MockProvider


def _sanitize_reply(text: str, max_len: int = 160) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3] + "..."


def _short_session(session_id: str | None) -> str:
    if not session_id:
        return "-"
    return f"{session_id[:8]}...{session_id[-4:]}"


def _post_chat(client: TestClient, message: str, session_id: str | None = None) -> dict:
    payload = {"message": message}
    if session_id is not None:
        payload["session_id"] = session_id
    response = client.post("/api/v1/chat", json=payload)
    body = response.json()
    return {
        "status": response.status_code,
        "body": body,
    }


def _repo_data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "app" / "data"


def _build_client() -> TestClient:
    from app.main import create_app

    repos = create_repositories(_repo_data_dir())
    classifier = IntentClassifier(
        LLMManager(primary_provider=MockProvider(content="credit_limit"))
    )
    deps = GraphDependencies(
        customer_repository=repos.customer_repository,
        score_limit_repository=repos.score_limit_repository,
        credit_request_repository=repos.credit_request_repository,
        exchange_provider=None,
        intent_classifier=classifier,
    )
    # Routing-only diagnostic mode: stop right before credit_node to verify
    # that intent classification hands off to credit. This means step state
    # remains IDENTIFYING_INTENT while agent is already mapped to credit.
    graph = build_graph(deps, interrupt_before=["credit_node"])

    app = create_app()
    app.dependency_overrides[get_app_graph] = lambda: graph
    return TestClient(app)


def _print_step(step: int, result: dict) -> None:
    body = result["body"]
    print(
        "step="
        + str(step)
        + " status="
        + str(result["status"])
        + " session="
        + _short_session(body.get("session_id"))
        + " agent="
        + str(body.get("agent"))
        + " state="
        + str(body.get("state"))
        + " ended="
        + str(body.get("ended"))
        + " reply="
        + _sanitize_reply(str(body.get("reply", "")))
        + " intent="
        + str(body.get("intent", "n/a"))
    )


def main() -> int:
    logging.disable(logging.CRITICAL)
    for logger_name in ("app.main", "app.api.chat", "app.api.dependencies"):
        logger = logging.getLogger(logger_name)
        logger.disabled = True
        logger.handlers = []
    client = _build_client()
    print("mode=routing_only interrupt_before=credit_node")

    messages = [
        "olá",
        "12345678901",
        "12-05-1990",
        "quero consultar meu limite",
    ]

    session_id: str | None = None
    for idx, message in enumerate(messages, start=1):
        result = _post_chat(client, message, session_id=session_id)
        _print_step(idx, result)
        session_id = result["body"].get("session_id", session_id)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
