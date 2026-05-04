"""
LLMManager — primary/fallback provider orchestrator.

Tries the primary provider; on failure, tries fallback if configured;
if all fail, raises LLMProviderError. Never mutates the request.
Agents and services must not know which provider was used.

Source of truth: ARCHITECTURE.md §7.1, §7.4, DECISIONS.md ADR-003,
TEST_PLAN.md §11 (Observability Validation).
"""

import time

from app.llm.provider import LLMProvider, LLMProviderError
from app.observability.llm_telemetry import (
    emit_llm_fallback_triggered,
    emit_llm_provider_called,
)
from app.schemas.llm import LLMProviderName, LLMRequest, LLMResponse


def _provider_name_value(provider: LLMProvider) -> str | None:
    """Best-effort label for a provider, used only in telemetry events."""
    explicit = getattr(provider, "provider_name", None)
    if isinstance(explicit, LLMProviderName):
        return explicit.value
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    cls_name = type(provider).__name__.lower()
    if "grok" in cls_name:
        return LLMProviderName.GROK.value
    if "openai" in cls_name:
        return LLMProviderName.OPENAI.value
    if "mock" in cls_name:
        return LLMProviderName.MOCK.value
    return cls_name or None


def _provider_model(provider: LLMProvider) -> str | None:
    model = getattr(provider, "model", None)
    return model if isinstance(model, str) and model else None


class LLMManager:
    """
    Orchestrates LLM provider fallback and emits per-attempt telemetry.

    Usage:
        manager = LLMManager(primary_provider=grok, fallback_provider=openai)
        response = manager.generate(request)

    ARCHITECTURE.md §7.1 invariant:
        Fallback must not change business outcomes.
        Agents must not be aware of which provider was used.

    Telemetry contract (TEST_PLAN.md §11):
        - Every attempt (primary or fallback) emits llm_provider_called.
        - When the fallback succeeds after a primary failure, an additional
          llm_fallback_triggered event is emitted.
        - Telemetry never includes prompts, structured context, or PII.
    """

    def __init__(
        self,
        primary_provider: LLMProvider,
        fallback_provider: LLMProvider | None = None,
    ) -> None:
        if primary_provider is None:
            raise ValueError(
                "LLMManager requires a primary_provider; got None."
            )
        self._primary = primary_provider
        self._fallback = fallback_provider

    def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Try primary provider; fall back if it fails.

        Args:
            request: LLMRequest — never mutated.

        Returns:
            LLMResponse with fallback_triggered=True if fallback was used,
            and latency_ms populated with the observed call duration.

        Raises:
            LLMProviderError: if all providers fail.
        """
        task = request.task
        primary_label = _provider_name_value(self._primary)
        primary_model = _provider_model(self._primary)
        primary_error_type: str | None = None

        start = time.perf_counter()
        try:
            response = self._primary.generate(request)
        except LLMProviderError as exc:
            latency_ms = (time.perf_counter() - start) * 1000.0
            primary_error_type = type(exc).__name__
            emit_llm_provider_called(
                task=task,
                provider=primary_label,
                model=primary_model,
                latency_ms=latency_ms,
                fallback_triggered=False,
                success=False,
                error_type=primary_error_type,
            )
        else:
            latency_ms = (time.perf_counter() - start) * 1000.0
            emit_llm_provider_called(
                task=task,
                provider=response.provider.value,
                model=response.model,
                latency_ms=latency_ms,
                fallback_triggered=False,
                success=True,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
            )
            return response.model_copy(update={"latency_ms": round(latency_ms, 3)})

        if self._fallback is not None:
            fallback_label = _provider_name_value(self._fallback)
            fallback_model = _provider_model(self._fallback)
            start_fb = time.perf_counter()
            try:
                response = self._fallback.generate(request)
            except LLMProviderError as exc:
                fb_latency_ms = (time.perf_counter() - start_fb) * 1000.0
                emit_llm_provider_called(
                    task=task,
                    provider=fallback_label,
                    model=fallback_model,
                    latency_ms=fb_latency_ms,
                    fallback_triggered=True,
                    success=False,
                    error_type=type(exc).__name__,
                )
            else:
                fb_latency_ms = (time.perf_counter() - start_fb) * 1000.0
                emit_llm_provider_called(
                    task=task,
                    provider=response.provider.value,
                    model=response.model,
                    latency_ms=fb_latency_ms,
                    fallback_triggered=True,
                    success=True,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                )
                emit_llm_fallback_triggered(
                    task=task,
                    primary_provider=primary_label,
                    primary_model=primary_model,
                    fallback_provider=response.provider.value,
                    fallback_model=response.model,
                    latency_ms=fb_latency_ms,
                    primary_error_type=primary_error_type,
                )
                return response.model_copy(
                    update={
                        "fallback_triggered": True,
                        "latency_ms": round(fb_latency_ms, 3),
                    }
                )

        raise LLMProviderError("all llm providers failed")
