"""
LLM telemetry helpers — emit AI-engineering observability events.

Source of truth: TEST_PLAN.md §11 (Observability Validation).

Required events surfaced by this module:
- llm_provider_called (every primary or fallback attempt)
- llm_fallback_triggered (only when a fallback succeeded after primary failure)

Each event must carry sanitized, non-PII metadata only:
- task, provider, model, latency_ms, input_tokens, output_tokens,
  fallback_triggered, success, error_type.

These helpers are pure logging utilities. They must not raise, must not call
LLM providers, and must not access network or filesystem.
"""

from __future__ import annotations

from typing import Any

from app.observability.logger import get_logger, log_event

_logger = get_logger("app.llm.telemetry")


def emit_llm_provider_called(
    *,
    task: str | None,
    provider: str | None,
    model: str | None,
    latency_ms: float | None,
    fallback_triggered: bool,
    success: bool,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    error_type: str | None = None,
) -> None:
    """Emit a single llm_provider_called event with sanitized metadata."""
    fields: dict[str, Any] = {
        "task": task,
        "provider": provider,
        "model": model,
        "latency_ms": _round_latency(latency_ms),
        "fallback_triggered": bool(fallback_triggered),
        "success": bool(success),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    if error_type:
        fields["error_type"] = error_type
    log_event(_logger, "llm_provider_called", **fields)


def emit_llm_fallback_triggered(
    *,
    task: str | None,
    primary_provider: str | None,
    primary_model: str | None,
    fallback_provider: str | None,
    fallback_model: str | None,
    latency_ms: float | None,
    primary_error_type: str | None = None,
) -> None:
    """Emit a single llm_fallback_triggered event when fallback succeeded."""
    log_event(
        _logger,
        "llm_fallback_triggered",
        task=task,
        primary_provider=primary_provider,
        primary_model=primary_model,
        fallback_provider=fallback_provider,
        fallback_model=fallback_model,
        latency_ms=_round_latency(latency_ms),
        primary_error_type=primary_error_type,
    )


def _round_latency(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None
