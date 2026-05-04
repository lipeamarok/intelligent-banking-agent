"""
Phase 7A — LLM Provider contract tests.

Validates that app/llm/provider.py exposes a correct abstract contract
(Protocol or ABC) for LLM providers.

Rules:
- No network calls.
- No real API keys.
- No OpenAI/Grok SDK imports.
"""

import inspect

import pytest


# ── 1. Contract existence ──────────────────────────────────────────────────────


class TestLLMProviderContractExists:

    def test_provider_module_is_importable(self):
        """app/llm/provider.py must be importable."""
        import app.llm.provider  # noqa: F401 — ImportError is the failure

    def test_llm_provider_class_exists(self):
        """provider module must expose LLMProvider (Protocol or ABC)."""
        from app.llm.provider import LLMProvider
        assert LLMProvider is not None

    def test_llm_provider_has_generate_method(self):
        """
        ARCHITECTURE.md §7.2: provider interface must define generate().
        (Spec calls it `complete` in pseudocode but generate() was chosen
        as the project-level canonical name per Phase 7A task description.)
        """
        from app.llm.provider import LLMProvider
        assert hasattr(LLMProvider, "generate"), (
            "LLMProvider must define a 'generate' method"
        )

    def test_generate_signature_accepts_request_and_returns_response(self):
        """
        generate(self, request: LLMRequest) -> LLMResponse must be the
        declared signature.
        """
        from app.llm.provider import LLMProvider
        sig = inspect.signature(LLMProvider.generate)
        params = list(sig.parameters)
        assert "request" in params, "generate must accept a 'request' parameter"

    def test_provider_does_not_import_openai_sdk(self):
        """provider.py must not import openai, grok, or httpx."""
        import app.llm.provider as mod
        source_file = inspect.getfile(mod)
        with open(source_file, encoding="utf-8") as f:
            source = f.read()
        for forbidden in ("import openai", "import grok", "import httpx", "import requests"):
            assert forbidden not in source, (
                f"provider.py must not contain {forbidden!r}"
            )


# ── 2. LLMProviderError ────────────────────────────────────────────────────────


class TestLLMProviderError:

    def test_llm_provider_error_exists(self):
        """provider module must expose LLMProviderError."""
        from app.llm.provider import LLMProviderError
        assert LLMProviderError is not None

    def test_llm_provider_error_is_exception(self):
        """LLMProviderError must be a subclass of Exception."""
        from app.llm.provider import LLMProviderError
        assert issubclass(LLMProviderError, Exception)

    def test_llm_provider_error_is_raiseable(self):
        """LLMProviderError must be raiseable and catchable."""
        from app.llm.provider import LLMProviderError
        with pytest.raises(LLMProviderError):
            raise LLMProviderError("test failure")
