"""Phase 7E — OpenAIProvider unit tests with fake HTTP client (no network)."""

import pytest

from app.llm.provider import LLMProviderError
from app.schemas.llm import LLMProviderName, LLMRequest


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None, raise_exc: Exception | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self._raise_exc = raise_exc

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self._raise_exc is not None:
            raise self._raise_exc
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHTTPClient:
    def __init__(self, response: FakeResponse | None = None, post_exc: Exception | None = None) -> None:
        self.response = response or FakeResponse()
        self.post_exc = post_exc
        self.calls: list[dict] = []

    def post(self, url: str, headers: dict, json: dict, timeout: float):
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        if self.post_exc is not None:
            raise self.post_exc
        return self.response


def _request() -> LLMRequest:
    return LLMRequest(prompt="classify", structured_context={"state": "IDENTIFYING_INTENT"}, max_tokens=40)


def test_openai_provider_success_returns_llm_response():
    from app.llm.openai_provider import OpenAIProvider

    fake_client = FakeHTTPClient(
        response=FakeResponse(
            payload={
                "choices": [{"message": {"content": "exchange_quote"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 4},
            }
        )
    )
    provider = OpenAIProvider(
        api_key="test-key",
        base_url="https://api.openai.com/v1/chat/completions",
        model="gpt-test",
        http_client=fake_client,
    )

    response = provider.generate(_request())
    assert response.content == "exchange_quote"
    assert response.provider == LLMProviderName.OPENAI
    assert response.model == "gpt-test"
    assert response.input_tokens == 11
    assert response.output_tokens == 4


def test_openai_provider_posts_expected_payload():
    from app.llm.openai_provider import OpenAIProvider

    fake_client = FakeHTTPClient(response=FakeResponse(payload={"choices": [{"message": {"content": "unknown"}}]}))
    provider = OpenAIProvider(
        api_key="test-key",
        base_url="https://api.openai.com/v1/chat/completions",
        model="gpt-test",
        http_client=fake_client,
        timeout=7.0,
    )

    req = _request()
    provider.generate(req)

    assert len(fake_client.calls) == 1
    call = fake_client.calls[0]
    assert call["url"] == "https://api.openai.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer test-key"
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["timeout"] == 7.0
    assert call["json"]["model"] == "gpt-test"
    assert isinstance(call["json"].get("messages"), list)
    assert req.prompt in call["json"]["messages"][1]["content"]
    assert "IDENTIFYING_INTENT" in call["json"]["messages"][1]["content"]
    assert call["json"]["max_tokens"] == 40


def test_openai_provider_missing_api_key_raises():
    from app.llm.openai_provider import OpenAIProvider

    with pytest.raises((ValueError, LLMProviderError)):
        OpenAIProvider(api_key="", http_client=FakeHTTPClient())


def test_openai_provider_http_error_raises_provider_error():
    from app.llm.openai_provider import OpenAIProvider

    fake_client = FakeHTTPClient(response=FakeResponse(status_code=429))
    provider = OpenAIProvider(api_key="test-key", http_client=fake_client)

    with pytest.raises(LLMProviderError):
        provider.generate(_request())


def test_openai_provider_malformed_response_raises_provider_error():
    from app.llm.openai_provider import OpenAIProvider

    fake_client = FakeHTTPClient(response=FakeResponse(payload={"choices": []}))
    provider = OpenAIProvider(api_key="test-key", http_client=fake_client)

    with pytest.raises(LLMProviderError):
        provider.generate(_request())


def test_openai_provider_timeout_or_client_exception_raises_provider_error():
    from app.llm.openai_provider import OpenAIProvider

    fake_client = FakeHTTPClient(post_exc=RuntimeError("timeout"))
    provider = OpenAIProvider(api_key="test-key", http_client=fake_client)

    with pytest.raises(LLMProviderError):
        provider.generate(_request())


def test_openai_provider_does_not_log_or_return_api_key():
    from app.llm.openai_provider import OpenAIProvider

    secret = "super-secret-key"
    fake_client = FakeHTTPClient(post_exc=RuntimeError("transport failure"))
    provider = OpenAIProvider(api_key=secret, http_client=fake_client)

    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate(_request())

    assert secret not in str(exc_info.value)
