"""
Phase 7A — MockProvider tests.

Validates that MockProvider is deterministic, injectable, and never
touches the network or filesystem.

Rules:
- No network calls.
- No real API keys.
- No OpenAI/Grok SDK imports.
"""

import pytest

from app.schemas.llm import LLMProviderName, LLMRequest


# ── 3. MockProvider returns configured response ───────────────────────────────


class TestMockProviderReturnsConfiguredResponse:

    def test_returns_configured_content(self):
        """
        MockProvider(content="credit_limit") must return
        LLMResponse.content == "credit_limit".
        """
        from app.llm.mock_provider import MockProvider
        provider = MockProvider(content="credit_limit")
        request = LLMRequest(prompt="What is my limit?")
        response = provider.generate(request)
        assert response.content == "credit_limit"

    def test_provider_name_is_mock(self):
        """Response.provider must be LLMProviderName.MOCK."""
        from app.llm.mock_provider import MockProvider
        provider = MockProvider(content="ok")
        response = provider.generate(LLMRequest(prompt="test"))
        assert response.provider == LLMProviderName.MOCK

    def test_fallback_triggered_is_false(self):
        """MockProvider normal response must have fallback_triggered == False."""
        from app.llm.mock_provider import MockProvider
        provider = MockProvider(content="ok")
        response = provider.generate(LLMRequest(prompt="test"))
        assert response.fallback_triggered is False

    def test_model_reflects_configured_value(self):
        """Response.model must match the model passed to MockProvider."""
        from app.llm.mock_provider import MockProvider
        provider = MockProvider(content="x", model="test-model-v1")
        response = provider.generate(LLMRequest(prompt="test"))
        assert response.model == "test-model-v1"

    def test_default_model_is_mock_model(self):
        """Default model name must be 'mock-model'."""
        from app.llm.mock_provider import MockProvider
        provider = MockProvider()
        response = provider.generate(LLMRequest(prompt="test"))
        assert response.model == "mock-model"


# ── 4. MockProvider records requests ─────────────────────────────────────────


class TestMockProviderRecordsRequests:

    def test_requests_list_starts_empty(self):
        """MockProvider.requests must be an empty list on creation."""
        from app.llm.mock_provider import MockProvider
        provider = MockProvider()
        assert provider.requests == []

    def test_generate_appends_to_requests(self):
        """Each generate() call must append the request to provider.requests."""
        from app.llm.mock_provider import MockProvider
        provider = MockProvider(content="ok")
        req1 = LLMRequest(prompt="first")
        req2 = LLMRequest(prompt="second")
        provider.generate(req1)
        provider.generate(req2)
        assert len(provider.requests) == 2
        assert provider.requests[0] is req1
        assert provider.requests[1] is req2

    def test_requests_list_is_inspectable(self):
        """Stored request must preserve structured_context."""
        from app.llm.mock_provider import MockProvider
        provider = MockProvider(content="ok")
        req = LLMRequest(prompt="test", structured_context={"state": "CREDIT"})
        provider.generate(req)
        assert provider.requests[0].structured_context == {"state": "CREDIT"}


# ── 5. MockProvider can fail ──────────────────────────────────────────────────


class TestMockProviderCanFail:

    def test_should_fail_raises_llm_provider_error(self):
        """
        MockProvider(should_fail=True) must raise LLMProviderError on generate().
        """
        from app.llm.mock_provider import MockProvider
        from app.llm.provider import LLMProviderError
        provider = MockProvider(should_fail=True)
        with pytest.raises(LLMProviderError):
            provider.generate(LLMRequest(prompt="will fail"))

    def test_should_fail_error_message_is_informative(self):
        """Error message must not be empty."""
        from app.llm.mock_provider import MockProvider
        from app.llm.provider import LLMProviderError
        provider = MockProvider(should_fail=True)
        with pytest.raises(LLMProviderError) as exc_info:
            provider.generate(LLMRequest(prompt="fail"))
        assert len(str(exc_info.value)) > 0

    def test_should_fail_does_not_append_to_requests(self):
        """A failing generate() must not record the request."""
        from app.llm.mock_provider import MockProvider
        from app.llm.provider import LLMProviderError
        provider = MockProvider(should_fail=True)
        with pytest.raises(LLMProviderError):
            provider.generate(LLMRequest(prompt="fail"))
        assert provider.requests == []


# ── 6. MockProvider does not require API key ──────────────────────────────────


class TestMockProviderDoesNotRequireAPIKey:

    def test_instantiation_without_env_vars(self, monkeypatch):
        """
        MockProvider must not read any environment variable.
        Remove all XAI/OPENAI env vars — instantiation must succeed.
        """
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from app.llm.mock_provider import MockProvider
        provider = MockProvider(content="ok")
        assert provider is not None

    def test_generate_without_env_vars(self, monkeypatch):
        """generate() must succeed without any environment variable set."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from app.llm.mock_provider import MockProvider
        provider = MockProvider(content="no-key-needed")
        response = provider.generate(LLMRequest(prompt="test"))
        assert response.content == "no-key-needed"

    def test_mock_provider_does_not_import_http_libraries(self):
        """mock_provider.py must not import requests, httpx, openai, grok."""
        import inspect
        import app.llm.mock_provider as mod
        source_file = inspect.getfile(mod)
        with open(source_file, encoding="utf-8") as f:
            source = f.read()
        for forbidden in ("import openai", "import grok", "import httpx", "import requests"):
            assert forbidden not in source, (
                f"mock_provider.py must not contain {forbidden!r}"
            )
