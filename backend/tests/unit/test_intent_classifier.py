"""Phase 7B — IntentClassifier unit tests."""

import inspect

import pytest

from app.llm.manager import LLMManager
from app.llm.mock_provider import MockProvider
from app.schemas.common import Intent


def _make_classifier(content: str = "unknown", should_fail: bool = False):
    from app.llm.intent_classifier import IntentClassifier

    manager = LLMManager(primary_provider=MockProvider(content=content, should_fail=should_fail))
    return IntentClassifier(manager), manager


def test_intent_classifier_maps_credit_limit():
    clf, _ = _make_classifier(content="credit_limit")
    assert clf.classify("quero consultar limite") == Intent.CREDIT_LIMIT


def test_intent_classifier_maps_credit_increase():
    clf, _ = _make_classifier(content="credit_increase")
    assert clf.classify("quero aumentar limite") == Intent.CREDIT_INCREASE


def test_intent_classifier_maps_credit_interview():
    clf, _ = _make_classifier(content="credit_interview")
    assert clf.classify("aceito entrevista") == Intent.CREDIT_INTERVIEW


def test_intent_classifier_maps_exchange_quote():
    clf, _ = _make_classifier(content="exchange_quote")
    assert clf.classify("cotação dólar") == Intent.EXCHANGE_QUOTE


def test_intent_classifier_maps_end_conversation():
    clf, _ = _make_classifier(content="end_conversation")
    assert clf.classify("encerrar") == Intent.END_CONVERSATION


def test_intent_classifier_maps_unknown():
    clf, _ = _make_classifier(content="unknown")
    assert clf.classify("oi") == Intent.UNKNOWN


def test_intent_classifier_strips_and_lowercases_output():
    clf, _ = _make_classifier(content="  CREDIT_LIMIT  ")
    assert clf.classify("quero limite") == Intent.CREDIT_LIMIT


def test_intent_classifier_rejects_invalid_output():
    clf, _ = _make_classifier(content="anything else")
    assert clf.classify("quero limite") == Intent.UNKNOWN


@pytest.mark.parametrize(
    "node_name",
    ["credit_node", "exchange_node", "ending_node", "triage_node", "intent_node"],
)
def test_intent_classifier_rejects_node_names(node_name: str):
    clf, _ = _make_classifier(content=node_name)
    assert clf.classify("quero limite") == Intent.UNKNOWN


def test_intent_classifier_rejects_verbose_output():
    clf, _ = _make_classifier(content="A intenção é credit_limit porque o usuário pediu limite")
    assert clf.classify("quero limite") == Intent.UNKNOWN


def test_intent_classifier_rejects_multiline_output():
    clf, _ = _make_classifier(content="credit_limit\nextra")
    assert clf.classify("quero limite") == Intent.UNKNOWN


def test_intent_classifier_handles_provider_failure_as_unknown():
    clf, manager = _make_classifier(should_fail=True)
    assert clf.classify("quero limite") == Intent.UNKNOWN
    assert len(manager._primary.requests) == 0


@pytest.mark.parametrize("message", ["", "   "])
def test_intent_classifier_empty_message_returns_unknown(message: str):
    clf, manager = _make_classifier(content="credit_limit")
    assert clf.classify(message) == Intent.UNKNOWN
    assert len(manager._primary.requests) == 0


def test_intent_classifier_requires_manager():
    from app.llm.intent_classifier import IntentClassifier

    with pytest.raises((TypeError, ValueError)):
        IntentClassifier(None)  # type: ignore[arg-type]


def test_intent_classifier_sends_structured_context():
    clf, manager = _make_classifier(content="credit_limit")

    message = "quero limite"
    result = clf.classify(message)
    assert result == Intent.CREDIT_LIMIT

    assert len(manager._primary.requests) == 1
    req = manager._primary.requests[0]
    assert "allowed_intents" in req.structured_context
    assert "user_message" in req.structured_context
    assert "constraints" in req.structured_context
    assert req.structured_context["user_message"] == message


def test_intent_classifier_does_not_mutate_input():
    clf, _ = _make_classifier(content="credit_limit")
    message = "quero limite"

    original = message
    _ = clf.classify(message)

    assert message == original


def test_intent_classifier_does_not_call_network_or_require_env():
    import app.llm.intent_classifier as mod

    source_file = inspect.getfile(mod)
    with open(source_file, encoding="utf-8") as f:
        source = f.read()

    for forbidden in ("import requests", "import httpx", "import openai", "import grok"):
        assert forbidden not in source
