"""Unit tests for LLMManager telemetry: latency, log events, fallback trace."""

import logging
from contextlib import contextmanager

import pytest

from app.llm.manager import LLMManager
from app.llm.mock_provider import MockProvider
from app.llm.provider import LLMProviderError
from app.schemas.llm import LLMRequest


def _make_manager(primary, fallback=None) -> LLMManager:
    return LLMManager(primary_provider=primary, fallback_provider=fallback)


@contextmanager
def _capture_telemetry():
    """Attach a handler directly to the telemetry logger.

    Required because app/observability/logger.py sets propagate=False, which
    prevents pytest's caplog (root-based) from intercepting the records.
    """
    logger = logging.getLogger("app.llm.telemetry")
    records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Collector(level=logging.INFO)
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)


def _messages(records, event_name: str) -> list[str]:
    return [r.getMessage() for r in records if event_name in r.getMessage()]


class TestLLMManagerLatency:
    def test_primary_response_carries_latency_ms(self):
        primary = MockProvider(content="ok")
        result = _make_manager(primary).generate(LLMRequest(prompt="x"))
        assert isinstance(result.latency_ms, float)
        assert result.latency_ms >= 0.0

    def test_fallback_response_carries_latency_and_flag(self):
        primary = MockProvider(should_fail=True)
        fallback = MockProvider(content="ok")
        result = _make_manager(primary, fallback).generate(LLMRequest(prompt="x"))
        assert result.fallback_triggered is True
        assert isinstance(result.latency_ms, float)


class TestLLMManagerObservabilityEvents:
    def test_emits_llm_provider_called_on_primary_success(self):
        primary = MockProvider(content="ok", model="mock-1")
        with _capture_telemetry() as records:
            _make_manager(primary).generate(
                LLMRequest(prompt="x", task="intent_classification")
            )
        called = _messages(records, "llm_provider_called")
        assert len(called) == 1
        assert "intent_classification" in called[0]
        assert '"success": "True"' in called[0]
        assert '"fallback_triggered": "False"' in called[0]

    def test_emits_two_provider_called_events_on_fallback_path(self):
        primary = MockProvider(should_fail=True)
        fallback = MockProvider(content="ok", model="mock-fb")
        with _capture_telemetry() as records:
            _make_manager(primary, fallback).generate(
                LLMRequest(prompt="x", task="intent_classification")
            )
        called = _messages(records, "llm_provider_called")
        fb = _messages(records, "llm_fallback_triggered")
        assert len(called) == 2
        assert len(fb) == 1
        assert '"success": "False"' in called[0]
        assert '"fallback_triggered": "True"' in called[1]
        assert "intent_classification" in fb[0]

    def test_no_fallback_event_when_both_providers_fail(self):
        primary = MockProvider(should_fail=True)
        fallback = MockProvider(should_fail=True)
        with _capture_telemetry() as records:
            with pytest.raises(LLMProviderError):
                _make_manager(primary, fallback).generate(LLMRequest(prompt="x"))
        called = _messages(records, "llm_provider_called")
        fb = _messages(records, "llm_fallback_triggered")
        assert len(called) == 2
        assert all('"success": "False"' in m for m in called)
        assert fb == []


class TestLLMManagerSecurity:
    def test_telemetry_does_not_log_prompt_or_context(self):
        primary = MockProvider(content="ok")
        with _capture_telemetry() as records:
            _make_manager(primary).generate(
                LLMRequest(
                    prompt="SECRET-PROMPT-MARKER",
                    structured_context={"user_message": "SECRET-CTX-MARKER"},
                    task="intent_classification",
                )
            )
        for record in records:
            msg = record.getMessage()
            assert "SECRET-PROMPT-MARKER" not in msg
            assert "SECRET-CTX-MARKER" not in msg
