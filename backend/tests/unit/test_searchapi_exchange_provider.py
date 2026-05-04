"""Unit tests for SearchApiExchangeProvider with fake HTTP client."""

import inspect

import pytest

from app.exchange.provider import ExchangeProviderError


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
    def __init__(self, response: FakeResponse | None = None, get_exc: Exception | None = None) -> None:
        self.response = response or FakeResponse()
        self.get_exc = get_exc
        self.calls: list[dict] = []

    def get(self, url: str, params: dict, timeout: float):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if self.get_exc is not None:
            raise self.get_exc
        return self.response


def _valid_payload(rate: float = 5.25) -> dict:
    return {
        "answer_box": {
            "type": "currency_converter",
            "answer": "1 Brazilian Real is equal 0.2 United States Dollar",
            "price": rate,
            "currency": "United States Dollar",
            "from": {"price": 1, "currency": "Brazilian Real"},
            "to": {"price": rate, "currency": "United States Dollar"},
        }
    }


def _legacy_payload(rate: float = 5.25) -> dict:
    return {
        "answer_box": {
            "currency_converter": {
                "exchange_rate": rate,
                "from": "BRL",
                "to": "USD",
            }
        }
    }


def test_searchapi_exchange_provider_success_returns_exchange_quote():
    from app.exchange.searchapi_provider import SearchApiExchangeProvider

    provider = SearchApiExchangeProvider(
        api_key="test-key",
        http_client=FakeHTTPClient(response=FakeResponse(payload=_valid_payload(5.25))),
    )

    quote = provider.get_quote("BRL", "USD")
    assert quote["rate"] == 5.25
    assert quote["base_currency"] == "BRL"
    assert quote["target_currency"] == "USD"
    assert quote["provider"] == "searchapi"


def test_searchapi_exchange_provider_supports_legacy_nested_rate_shape():
    from app.exchange.searchapi_provider import SearchApiExchangeProvider

    provider = SearchApiExchangeProvider(
        api_key="test-key",
        http_client=FakeHTTPClient(response=FakeResponse(payload=_legacy_payload(4.95))),
    )

    quote = provider.get_quote("BRL", "USD")
    assert quote["rate"] == 4.95


def test_searchapi_exchange_provider_sends_expected_params():
    from app.exchange.searchapi_provider import SearchApiExchangeProvider

    fake_client = FakeHTTPClient(response=FakeResponse(payload=_valid_payload(5.25)))
    provider = SearchApiExchangeProvider(
        api_key="test-key",
        base_url="https://www.searchapi.io/api/v1/search",
        http_client=fake_client,
        timeout=4.0,
    )

    provider.get_quote("BRL", "USD")
    assert len(fake_client.calls) == 1
    call = fake_client.calls[0]
    assert call["url"] == "https://www.searchapi.io/api/v1/search"
    assert call["params"]["api_key"] == "test-key"
    assert call["params"]["engine"] == "google"
    assert "BRL" in call["params"]["q"]
    assert "USD" in call["params"]["q"]
    assert call["timeout"] == 4.0


def test_searchapi_exchange_provider_missing_api_key_raises():
    from app.exchange.searchapi_provider import SearchApiExchangeProvider

    with pytest.raises((ValueError, ExchangeProviderError)):
        SearchApiExchangeProvider(api_key="", http_client=FakeHTTPClient())


@pytest.mark.parametrize("status", [400, 500])
def test_searchapi_exchange_provider_http_error_raises(status: int):
    from app.exchange.searchapi_provider import SearchApiExchangeProvider

    provider = SearchApiExchangeProvider(
        api_key="test-key",
        http_client=FakeHTTPClient(response=FakeResponse(status_code=status)),
    )
    with pytest.raises(ExchangeProviderError):
        provider.get_quote("BRL", "USD")


def test_searchapi_exchange_provider_malformed_response_raises():
    from app.exchange.searchapi_provider import SearchApiExchangeProvider

    provider = SearchApiExchangeProvider(
        api_key="test-key",
        http_client=FakeHTTPClient(response=FakeResponse(payload={"answer_box": {}})),
    )
    with pytest.raises(ExchangeProviderError):
        provider.get_quote("BRL", "USD")


@pytest.mark.parametrize("rate", [0, -1])
def test_searchapi_exchange_provider_negative_or_zero_rate_raises(rate: float):
    from app.exchange.searchapi_provider import SearchApiExchangeProvider

    provider = SearchApiExchangeProvider(
        api_key="test-key",
        http_client=FakeHTTPClient(response=FakeResponse(payload=_valid_payload(rate))),
    )
    with pytest.raises(ExchangeProviderError):
        provider.get_quote("BRL", "USD")


def test_searchapi_exchange_provider_client_exception_raises():
    from app.exchange.searchapi_provider import SearchApiExchangeProvider

    provider = SearchApiExchangeProvider(
        api_key="test-key",
        http_client=FakeHTTPClient(get_exc=RuntimeError("connection issue")),
    )
    with pytest.raises(ExchangeProviderError):
        provider.get_quote("BRL", "USD")


def test_searchapi_exchange_provider_does_not_leak_api_key():
    from app.exchange.searchapi_provider import SearchApiExchangeProvider

    secret = "very-secret-key"
    provider = SearchApiExchangeProvider(
        api_key=secret,
        http_client=FakeHTTPClient(get_exc=RuntimeError("connection issue")),
    )
    with pytest.raises(ExchangeProviderError) as exc_info:
        provider.get_quote("BRL", "USD")
    assert secret not in str(exc_info.value)


def test_searchapi_exchange_provider_does_not_require_real_env(monkeypatch):
    from app.exchange.searchapi_provider import SearchApiExchangeProvider

    monkeypatch.delenv("EXCHANGE_API_KEY", raising=False)
    monkeypatch.delenv("SEARCHAPI_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)

    provider = SearchApiExchangeProvider(
        api_key="test-key",
        http_client=FakeHTTPClient(response=FakeResponse(payload=_valid_payload(5.25))),
    )
    quote = provider.get_quote("BRL", "USD")
    assert quote["rate"] == 5.25


def test_searchapi_exchange_provider_does_not_import_external_sdks():
    import app.exchange.searchapi_provider as mod

    source_file = inspect.getfile(mod)
    with open(source_file, encoding="utf-8") as f:
        source = f.read()

    for forbidden in (
        "import searchapi",
        "from searchapi",
        "import tavily",
        "from tavily",
        "import langchain",
    ):
        assert forbidden not in source
