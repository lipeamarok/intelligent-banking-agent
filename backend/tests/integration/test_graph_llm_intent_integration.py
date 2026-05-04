"""Phase 7C — Graph integration with app.llm.IntentClassifier + MockProvider."""

import inspect

from app.graph.dependencies import GraphDependencies
from app.graph.graph_builder import build_graph
from app.llm.intent_classifier import IntentClassifier
from app.llm.manager import LLMManager
from app.llm.mock_provider import MockProvider
from app.schemas.common import Intent
from tests.conftest import (
    ANA,
    CARLOS,
    MARINA,
    FakeCreditRequestRepository,
    FakeCustomerRepository,
    FakeExchangeProvider,
    FakeScoreLimitRepository,
)


def _cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _deps_with_classifier(provider: MockProvider) -> tuple[GraphDependencies, MockProvider, FakeExchangeProvider]:
    exchange = FakeExchangeProvider(rate=5.0, should_fail=False)
    classifier = IntentClassifier(LLMManager(primary_provider=provider))
    deps = GraphDependencies(
        customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA]),
        score_limit_repository=FakeScoreLimitRepository(),
        credit_request_repository=FakeCreditRequestRepository(),
        exchange_provider=exchange,
        intent_classifier=classifier,
    )
    return deps, provider, exchange


def _auth_first_turn(graph, thread_id: str) -> dict:
    return dict(
        graph.invoke(
            {
                "session_id": f"s-{thread_id}",
                "trace_id": f"t-{thread_id}",
                "cpf_candidate": ANA.cpf,
                "birth_date_candidate": ANA.data_nascimento,
            },
            config=_cfg(thread_id),
        )
    )


def _resume_after_auth_handoff(graph, thread_id: str) -> dict:
    state = dict(graph.invoke(None, config=_cfg(thread_id)))
    for _ in range(3):
        if state.get("current_state") != "AUTHENTICATED":
            break
        state = dict(graph.invoke(None, config=_cfg(thread_id)))
    return state


def test_graph_uses_intent_classifier_for_credit_limit():
    provider = MockProvider(content="credit_limit")
    deps, provider, _ = _deps_with_classifier(provider)
    graph = build_graph(deps, interrupt_before=["intent_node"])

    s1 = _auth_first_turn(graph, "llm-credit-01")
    assert s1.get("authenticated") is True

    graph.update_state(_cfg("llm-credit-01"), {"last_user_input": "quero consultar limite"})
    s2 = _resume_after_auth_handoff(graph, "llm-credit-01")

    assert s2.get("current_state") == "SHOWING_CREDIT_LIMIT"
    assert len(provider.requests) == 1
    assert provider.requests[0].structured_context.get("user_message") == "quero consultar limite"


def test_graph_uses_intent_classifier_for_exchange_quote():
    provider = MockProvider(content="exchange_quote")
    deps, _, exchange = _deps_with_classifier(provider)
    graph = build_graph(deps, interrupt_before=["intent_node"])

    s1 = _auth_first_turn(graph, "llm-exch-01")
    assert s1.get("authenticated") is True

    graph.update_state(
        _cfg("llm-exch-01"),
        {
            "last_user_input": "quero cotação",
            "exchange_request": {"base_currency": "BRL", "target_currency": "USD"},
        },
    )
    s2 = _resume_after_auth_handoff(graph, "llm-exch-01")

    assert s2.get("current_state") == "EXCHANGE_SHOWING_QUOTE"
    assert len(exchange.calls) >= 1


def test_graph_invalid_llm_output_results_in_unknown_intent_flow():
    provider = MockProvider(content="credit_node")
    deps, provider, _ = _deps_with_classifier(provider)
    graph = build_graph(deps, interrupt_before=["intent_node"])

    _auth_first_turn(graph, "llm-invalid-01")
    graph.update_state(_cfg("llm-invalid-01"), {"last_user_input": "quero limite"})
    s2 = _resume_after_auth_handoff(graph, "llm-invalid-01")

    assert s2.get("intent") == Intent.UNKNOWN
    assert s2.get("current_state") == "IDENTIFYING_INTENT"
    assert s2.get("next_step") == "intent_node"
    assert len(provider.requests) == 1


def test_graph_llm_provider_failure_results_in_unknown_intent():
    provider = MockProvider(should_fail=True)
    deps, _, _ = _deps_with_classifier(provider)
    graph = build_graph(deps, interrupt_before=["intent_node"])

    _auth_first_turn(graph, "llm-fail-01")
    graph.update_state(_cfg("llm-fail-01"), {"last_user_input": "quero limite"})
    s2 = _resume_after_auth_handoff(graph, "llm-fail-01")

    assert s2.get("intent") == Intent.UNKNOWN
    assert s2.get("current_state") == "IDENTIFYING_INTENT"
    assert s2.get("next_step") == "intent_node"


def test_graph_intent_classifier_does_not_store_llm_manager_in_state():
    provider = MockProvider(content="credit_limit")
    deps, _, _ = _deps_with_classifier(provider)
    graph = build_graph(deps, interrupt_before=["intent_node"])

    _auth_first_turn(graph, "llm-state-01")
    graph.update_state(_cfg("llm-state-01"), {"last_user_input": "quero limite"})
    s2 = _resume_after_auth_handoff(graph, "llm-state-01")

    for forbidden in ("manager", "llm_manager", "provider", "intent_classifier"):
        assert forbidden not in s2


def test_graph_intent_classifier_does_not_call_real_provider():
    import app.llm.intent_classifier as ic_mod
    import app.llm.manager as manager_mod

    for mod in (ic_mod, manager_mod):
        source_file = inspect.getfile(mod)
        with open(source_file, encoding="utf-8") as f:
            source = f.read()
        for forbidden in ("import requests", "import httpx", "import openai", "import grok"):
            assert forbidden not in source
