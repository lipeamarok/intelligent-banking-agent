"""
Unit tests for app/schemas/llm.py
"""

import pytest
from pydantic import ValidationError

from app.schemas.llm import LLMProviderName, LLMRequest, LLMResponse


def test_llm_response_mock_provider():
    resp = LLMResponse(content="Olá!", provider=LLMProviderName.MOCK, model="mock-v1")
    assert resp.provider == LLMProviderName.MOCK
    assert resp.fallback_triggered is False


def test_llm_response_grok_provider():
    resp = LLMResponse(content="Resposta.", provider=LLMProviderName.GROK, model="grok-3")
    assert resp.provider == LLMProviderName.GROK


def test_llm_response_openai_provider():
    resp = LLMResponse(content="Resposta.", provider=LLMProviderName.OPENAI, model="gpt-4o")
    assert resp.provider == LLMProviderName.OPENAI


def test_llm_response_fallback_triggered_true():
    resp = LLMResponse(
        content="Fallback response.",
        provider=LLMProviderName.MOCK,
        model="mock-v1",
        fallback_triggered=True,
    )
    assert resp.fallback_triggered is True


def test_llm_response_fallback_triggered_false_by_default():
    resp = LLMResponse(content="ok", provider=LLMProviderName.OPENAI, model="gpt-4o")
    assert resp.fallback_triggered is False


def test_llm_response_token_counts_optional():
    resp = LLMResponse(
        content="ok",
        provider=LLMProviderName.GROK,
        model="grok-3",
        input_tokens=100,
        output_tokens=50,
    )
    assert resp.input_tokens == 100
    assert resp.output_tokens == 50


def test_llm_response_token_counts_default_none():
    resp = LLMResponse(content="ok", provider=LLMProviderName.MOCK, model="mock-v1")
    assert resp.input_tokens is None
    assert resp.output_tokens is None


def test_llm_request_defaults():
    req = LLMRequest(prompt="Qual é o limite do cliente?")
    assert req.structured_context == {}
    assert req.max_tokens is None


def test_llm_request_invalid_provider_fails():
    with pytest.raises(ValidationError):
        LLMResponse(content="ok", provider="unknown_provider", model="x")
