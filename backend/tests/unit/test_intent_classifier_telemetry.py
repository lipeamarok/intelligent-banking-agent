"""Unit tests for IntentClassifier.classify_with_telemetry()."""

from app.llm.intent_classifier import IntentClassifier
from app.llm.manager import LLMManager
from app.llm.mock_provider import MockProvider
from app.schemas.common import Intent


def _classifier(content: str = "credit_limit", should_fail: bool = False):
    manager = LLMManager(primary_provider=MockProvider(content=content, should_fail=should_fail))
    return IntentClassifier(manager)


def test_classify_with_telemetry_returns_triple_on_success():
    intent, classification, telemetry = _classifier("credit_limit").classify_with_telemetry(
        "quero meu limite"
    )
    assert intent == Intent.CREDIT_LIMIT
    assert classification.intent == "credit_limit"
    assert classification.confidence_bucket == "high"
    assert classification.ambiguous is False
    assert classification.should_clarify is False
    assert telemetry["task"] == IntentClassifier.TASK_NAME
    assert telemetry["provider"] == "mock"
    assert telemetry["fallback_triggered"] is False
    assert telemetry["safe_rationale"] == "exact_allowed_value"


def test_classify_with_telemetry_normalized_output_is_medium_confidence():
    intent, classification, _ = _classifier("  CREDIT_LIMIT  ").classify_with_telemetry(
        "quero limite"
    )
    assert intent == Intent.CREDIT_LIMIT
    assert classification.confidence_bucket == "medium"
    assert classification.safe_rationale == "normalized_allowed_value"


def test_classify_with_telemetry_rejects_node_name():
    intent, classification, telemetry = _classifier("credit_node").classify_with_telemetry(
        "quero limite"
    )
    assert intent == Intent.UNKNOWN
    assert classification.should_clarify is True
    assert classification.safe_rationale == "rejected_node_name"
    assert telemetry is not None


def test_classify_with_telemetry_rejects_multiline():
    intent, classification, _ = _classifier("credit_limit\nextra").classify_with_telemetry(
        "x"
    )
    assert intent == Intent.UNKNOWN
    assert classification.safe_rationale == "multiline_output"


def test_classify_with_telemetry_handles_provider_failure():
    intent, classification, telemetry = _classifier(should_fail=True).classify_with_telemetry(
        "quero limite"
    )
    assert intent == Intent.UNKNOWN
    assert classification.safe_rationale == "provider_error"
    assert telemetry is None


def test_classify_with_telemetry_empty_input_skips_provider():
    intent, classification, telemetry = _classifier().classify_with_telemetry("   ")
    assert intent == Intent.UNKNOWN
    assert classification.safe_rationale == "empty_input"
    assert telemetry is None


def test_classify_legacy_method_is_unchanged():
    # The legacy single-return classify() must keep its semantics.
    assert _classifier("credit_limit").classify("x") == Intent.CREDIT_LIMIT
    assert _classifier("garbage").classify("x") == Intent.UNKNOWN


def test_classify_request_carries_task_label():
    classifier = _classifier("credit_limit")
    classifier.classify_with_telemetry("quero limite")
    primary = classifier.manager._primary  # type: ignore[attr-defined]
    assert primary.requests[-1].task == IntentClassifier.TASK_NAME
