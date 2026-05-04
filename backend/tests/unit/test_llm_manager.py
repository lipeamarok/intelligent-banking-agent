"""
Phase 7A — LLMManager tests.

Validates primary/fallback orchestration, error propagation,
and request immutability.

Rules:
- No network calls.
- No real API keys.
- Only MockProvider is used.
"""

import pytest

from app.schemas.llm import LLMProviderName, LLMRequest


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_mock(content: str = "ok", should_fail: bool = False, model: str = "mock-model"):
    from app.llm.mock_provider import MockProvider
    return MockProvider(content=content, should_fail=should_fail, model=model)


# ── 7. LLMManager uses primary provider on success ───────────────────────────


class TestLLMManagerUsesPrimaryOnSuccess:

    def test_returns_primary_response_content(self):
        """
        When primary succeeds, manager must return primary's response.
        """
        from app.llm.manager import LLMManager
        primary = _make_mock(content="primary-answer")
        fallback = _make_mock(content="fallback-answer")
        manager = LLMManager(primary_provider=primary, fallback_provider=fallback)
        result = manager.generate(LLMRequest(prompt="test"))
        assert result.content == "primary-answer"

    def test_fallback_triggered_is_false_on_primary_success(self):
        """fallback_triggered must be False when primary succeeds."""
        from app.llm.manager import LLMManager
        primary = _make_mock(content="ok")
        manager = LLMManager(primary_provider=primary)
        result = manager.generate(LLMRequest(prompt="test"))
        assert result.fallback_triggered is False

    def test_fallback_provider_not_called_when_primary_succeeds(self):
        """Fallback provider must not receive any calls when primary succeeds."""
        from app.llm.manager import LLMManager
        primary = _make_mock(content="ok")
        fallback = _make_mock(content="should-not-be-called")
        manager = LLMManager(primary_provider=primary, fallback_provider=fallback)
        manager.generate(LLMRequest(prompt="test"))
        assert len(fallback.requests) == 0


# ── 8. LLMManager uses fallback when primary fails ────────────────────────────


class TestLLMManagerUsesFallbackOnPrimaryFailure:

    def test_returns_fallback_response_content(self):
        """
        When primary fails, manager must return fallback's response content.
        """
        from app.llm.manager import LLMManager
        primary = _make_mock(should_fail=True)
        fallback = _make_mock(content="fallback-answer")
        manager = LLMManager(primary_provider=primary, fallback_provider=fallback)
        result = manager.generate(LLMRequest(prompt="test"))
        assert result.content == "fallback-answer"

    def test_fallback_triggered_is_true_on_primary_failure(self):
        """fallback_triggered must be True when fallback was used."""
        from app.llm.manager import LLMManager
        primary = _make_mock(should_fail=True)
        fallback = _make_mock(content="ok")
        manager = LLMManager(primary_provider=primary, fallback_provider=fallback)
        result = manager.generate(LLMRequest(prompt="test"))
        assert result.fallback_triggered is True

    def test_fallback_provider_called_once_on_primary_failure(self):
        """Fallback must receive exactly one call when primary fails."""
        from app.llm.manager import LLMManager
        primary = _make_mock(should_fail=True)
        fallback = _make_mock(content="ok")
        manager = LLMManager(primary_provider=primary, fallback_provider=fallback)
        manager.generate(LLMRequest(prompt="test"))
        assert len(fallback.requests) == 1


# ── 9. LLMManager raises when all providers fail ─────────────────────────────


class TestLLMManagerRaisesWhenAllFail:

    def test_raises_llm_provider_error_when_all_fail(self):
        """
        When both primary and fallback fail, LLMProviderError must be raised.
        """
        from app.llm.manager import LLMManager
        from app.llm.provider import LLMProviderError
        primary = _make_mock(should_fail=True)
        fallback = _make_mock(should_fail=True)
        manager = LLMManager(primary_provider=primary, fallback_provider=fallback)
        with pytest.raises(LLMProviderError):
            manager.generate(LLMRequest(prompt="test"))

    def test_raises_when_no_fallback_and_primary_fails(self):
        """
        With no fallback configured and primary failing, must raise LLMProviderError.
        """
        from app.llm.manager import LLMManager
        from app.llm.provider import LLMProviderError
        primary = _make_mock(should_fail=True)
        manager = LLMManager(primary_provider=primary)
        with pytest.raises(LLMProviderError):
            manager.generate(LLMRequest(prompt="test"))

    def test_raised_error_has_informative_message(self):
        """LLMProviderError message must not be empty."""
        from app.llm.manager import LLMManager
        from app.llm.provider import LLMProviderError
        manager = LLMManager(primary_provider=_make_mock(should_fail=True))
        with pytest.raises(LLMProviderError) as exc_info:
            manager.generate(LLMRequest(prompt="test"))
        assert len(str(exc_info.value)) > 0


# ── 10. LLMManager requires primary provider ─────────────────────────────────


class TestLLMManagerRequiresPrimaryProvider:

    def test_none_primary_raises_value_error(self):
        """
        LLMManager(primary_provider=None) must raise ValueError or TypeError.
        """
        from app.llm.manager import LLMManager
        with pytest.raises((ValueError, TypeError)):
            LLMManager(primary_provider=None)

    def test_missing_primary_argument_raises(self):
        """Calling LLMManager() with no arguments must raise TypeError."""
        from app.llm.manager import LLMManager
        with pytest.raises(TypeError):
            LLMManager()  # type: ignore[call-arg]


# ── 11. LLMManager does not mutate request ────────────────────────────────────


class TestLLMManagerDoesNotMutateRequest:

    def test_original_request_unchanged_after_generate(self):
        """
        The request object passed to generate() must not be mutated.
        DECISIONS.md: LLM managers are infrastructure, not business logic.
        """
        from app.llm.manager import LLMManager
        primary = _make_mock(content="ok")
        manager = LLMManager(primary_provider=primary)
        req = LLMRequest(
            prompt="original prompt",
            structured_context={"state": "CREDIT", "user": "ANA"},
            max_tokens=100,
        )
        original_prompt = req.prompt
        original_context = dict(req.structured_context)
        original_max_tokens = req.max_tokens
        manager.generate(req)
        assert req.prompt == original_prompt
        assert req.structured_context == original_context
        assert req.max_tokens == original_max_tokens

    def test_request_context_preserved_after_fallback_path(self):
        """Request must not be mutated even when fallback path is taken."""
        from app.llm.manager import LLMManager
        primary = _make_mock(should_fail=True)
        fallback = _make_mock(content="ok")
        manager = LLMManager(primary_provider=primary, fallback_provider=fallback)
        req = LLMRequest(prompt="test", structured_context={"key": "value"})
        original_context = dict(req.structured_context)
        manager.generate(req)
        assert req.structured_context == original_context


# ── 12. LLMManager accepts structured context ────────────────────────────────


class TestLLMManagerAcceptsStructuredContext:

    def test_structured_context_forwarded_to_primary(self):
        """
        ARCHITECTURE.md §7.3: structured context must be forwarded to provider.
        The provider must receive the request with structured_context intact.
        """
        from app.llm.manager import LLMManager
        primary = _make_mock(content="ok")
        manager = LLMManager(primary_provider=primary)
        ctx = {"state": "IDENTIFYING_INTENT", "authenticated": True}
        req = LLMRequest(prompt="classify", structured_context=ctx)
        manager.generate(req)
        assert len(primary.requests) == 1
        assert primary.requests[0].structured_context == ctx

    def test_structured_context_forwarded_to_fallback(self):
        """Structured context must also be forwarded when fallback is used."""
        from app.llm.manager import LLMManager
        primary = _make_mock(should_fail=True)
        fallback = _make_mock(content="ok")
        manager = LLMManager(primary_provider=primary, fallback_provider=fallback)
        ctx = {"state": "test"}
        req = LLMRequest(prompt="test", structured_context=ctx)
        manager.generate(req)
        assert len(fallback.requests) == 1
        assert fallback.requests[0].structured_context == ctx
