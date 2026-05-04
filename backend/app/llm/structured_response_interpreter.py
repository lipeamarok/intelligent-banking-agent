"""Constrained LLM interpreter for normalizing short user replies safely."""

from __future__ import annotations

from app.llm.manager import LLMManager
from app.llm.provider import LLMProviderError
from app.schemas.llm import LLMRequest


class StructuredResponseInterpreter:
    """Interpret short user replies into a closed set of allowed values."""

    TASK_NAME = "structured_response_interpretation"

    def __init__(self, manager: LLMManager) -> None:
        if manager is None:
            raise ValueError("StructuredResponseInterpreter requires a manager; got None")
        self.manager = manager

    def interpret_choice(
        self,
        *,
        user_message: str,
        field_name: str,
        allowed_values: list[str],
        guidance: str,
        examples: dict[str, str] | None = None,
    ) -> str | None:
        """Return a single allowed value or None when interpretation is unsafe."""
        choice, _telemetry = self.interpret_choice_with_telemetry(
            user_message=user_message,
            field_name=field_name,
            allowed_values=allowed_values,
            guidance=guidance,
            examples=examples,
        )
        return choice

    def interpret_choice_with_telemetry(
        self,
        *,
        user_message: str,
        field_name: str,
        allowed_values: list[str],
        guidance: str,
        examples: dict[str, str] | None = None,
    ) -> tuple[str | None, dict | None]:
        """
        Same as interpret_choice() but also returns sanitized telemetry.

        Telemetry includes provider, model, fallback_triggered, latency_ms,
        tokens, and a safe_rationale describing why a result was accepted or
        rejected. Returns telemetry=None when no LLM call was attempted.
        """
        if not isinstance(user_message, str) or user_message.strip() == "":
            return None, None

        request = LLMRequest(
            prompt=(
                "Normalize the user's answer for a constrained banking workflow field. "
                "Return exactly one allowed value and nothing else."
            ),
            structured_context={
                "field_name": field_name,
                "guidance": guidance,
                "allowed_values": allowed_values,
                "user_message": user_message,
                "examples": examples or {},
            },
            max_tokens=8,
            task=self.TASK_NAME,
        )

        try:
            response = self.manager.generate(request)
        except LLMProviderError:
            return None, None

        content = response.content
        rationale = "rejected_unsafe_format"
        chosen: str | None = None

        if isinstance(content, str) and "\n" not in content and "\r" not in content:
            normalized = content.strip().lower()
            allowed_map = {value.lower(): value for value in allowed_values}
            if normalized in allowed_map:
                chosen = allowed_map[normalized]
                rationale = "matched_allowed_value"
            else:
                rationale = "not_in_allowed_values"

        telemetry = {
            "task": self.TASK_NAME,
            "provider": response.provider.value if response.provider else None,
            "model": response.model,
            "fallback_triggered": bool(response.fallback_triggered),
            "latency_ms": response.latency_ms,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "field_name": field_name,
            "matched": chosen is not None,
            "safe_rationale": rationale,
        }
        return chosen, telemetry
