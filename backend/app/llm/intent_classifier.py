"""Intent classifier backed by LLMManager with strict output validation."""

from app.llm.manager import LLMManager
from app.llm.prompts import CONSTRAINTS_BLOCK
from app.llm.provider import LLMProviderError
from app.schemas.common import Intent
from app.schemas.llm import IntentClassification, LLMRequest, LLMResponse


class IntentClassifier:
    """
    Classifies user text into an allowed Intent enum value.

    Safety rules:
    - Empty input returns UNKNOWN and does not call LLM.
    - LLM failures return UNKNOWN.
    - Only exact single-line matches to Intent values are accepted.
    - Node names and verbose outputs are always rejected.

    Telemetry contract (TEST_PLAN.md §11):
    - classify_with_telemetry() returns the chosen Intent plus a sanitized
      IntentClassification record (confidence_bucket, ambiguous, should_clarify,
      safe_rationale) and a per-call telemetry dict suitable for state
      propagation (provider_used, fallback_triggered, latency_ms, tokens).
    - The legacy classify() method is preserved unchanged from the caller's
      perspective and now delegates to classify_with_telemetry().
    """

    TASK_NAME = "intent_classification"

    _REJECTED_NODE_NAMES: frozenset[str] = frozenset(
        {"credit_node", "exchange_node", "ending_node", "triage_node", "intent_node"}
    )

    def __init__(self, manager: LLMManager) -> None:
        if manager is None:
            raise ValueError("IntentClassifier requires a manager; got None")
        self.manager = manager

    def classify(self, message: str) -> Intent:
        """Return a safe Intent classification for the provided message."""
        intent, _classification, _telemetry = self.classify_with_telemetry(message)
        return intent

    def classify_with_telemetry(
        self, message: str
    ) -> tuple[Intent, IntentClassification, dict | None]:
        """
        Classify message and return (intent, classification, telemetry).

        - intent: validated Intent enum (UNKNOWN on any safety failure).
        - classification: structured AI-engineering record (confidence,
          ambiguity, clarification flag, safe rationale). Never exposes raw
          LLM output.
        - telemetry: per-call observability dict or None if no LLM call was
          made (e.g. empty input). Includes provider, model, fallback_triggered,
          latency_ms, input_tokens, output_tokens.
        """
        if message is None or not isinstance(message, str) or message.strip() == "":
            return (
                Intent.UNKNOWN,
                IntentClassification(
                    intent=Intent.UNKNOWN.value,
                    confidence_bucket="low",
                    ambiguous=False,
                    should_clarify=False,
                    safe_rationale="empty_input",
                ),
                None,
            )

        request = LLMRequest(
            prompt=(
                "Classify the user's banking intent. "
                "Return exactly one allowed intent value."
            ),
            structured_context={
                "allowed_intents": [intent.value for intent in Intent],
                "user_message": message,
                "constraints": CONSTRAINTS_BLOCK,
            },
            task=self.TASK_NAME,
        )

        try:
            response = self.manager.generate(request)
        except LLMProviderError:
            return (
                Intent.UNKNOWN,
                IntentClassification(
                    intent=Intent.UNKNOWN.value,
                    confidence_bucket="low",
                    ambiguous=False,
                    should_clarify=False,
                    safe_rationale="provider_error",
                ),
                None,
            )

        intent_value, classification = self._validate_response(response)
        telemetry = _build_telemetry_record(response, classification)
        return intent_value, classification, telemetry

    def _validate_response(
        self, response: LLMResponse
    ) -> tuple[Intent, IntentClassification]:
        """Validate raw LLM content into (Intent, IntentClassification)."""
        content = response.content
        if not isinstance(content, str):
            return Intent.UNKNOWN, _unknown_classification("non_string_output")

        if "\n" in content or "\r" in content:
            return Intent.UNKNOWN, _unknown_classification("multiline_output")

        stripped = content.strip()
        if not stripped:
            return Intent.UNKNOWN, _unknown_classification("empty_output")

        normalized = stripped.lower()

        if normalized in self._REJECTED_NODE_NAMES:
            return Intent.UNKNOWN, _unknown_classification("rejected_node_name")

        try:
            intent_value = Intent(normalized)
        except ValueError:
            return Intent.UNKNOWN, _unknown_classification("not_in_allowed_intents")

        # Confidence heuristic: exact-allowed-value response gets "high";
        # if the model needed normalization (whitespace/case) we record "medium".
        if stripped == normalized:
            confidence: str = "high"
            rationale = "exact_allowed_value"
        else:
            confidence = "medium"
            rationale = "normalized_allowed_value"

        ambiguous = intent_value == Intent.UNKNOWN
        return (
            intent_value,
            IntentClassification(
                intent=intent_value.value,
                confidence_bucket=confidence,  # type: ignore[arg-type]
                ambiguous=ambiguous,
                should_clarify=ambiguous,
                safe_rationale=rationale,
            ),
        )


def _unknown_classification(reason: str) -> IntentClassification:
    return IntentClassification(
        intent=Intent.UNKNOWN.value,
        confidence_bucket="low",
        ambiguous=True,
        should_clarify=True,
        safe_rationale=reason,
    )


def _build_telemetry_record(
    response: LLMResponse, classification: IntentClassification
) -> dict:
    """Sanitized per-call telemetry for state propagation. No PII."""
    return {
        "task": IntentClassifier.TASK_NAME,
        "provider": response.provider.value if response.provider else None,
        "model": response.model,
        "fallback_triggered": bool(response.fallback_triggered),
        "latency_ms": response.latency_ms,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "confidence_bucket": classification.confidence_bucket,
        "ambiguous": classification.ambiguous,
        "should_clarify": classification.should_clarify,
        "safe_rationale": classification.safe_rationale,
    }
