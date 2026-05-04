"""SearchApi-backed exchange provider adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.exchange.provider import ExchangeProvider, ExchangeProviderError


class SearchApiExchangeProvider(ExchangeProvider):
    """Fetches exchange quotes from SearchApi with strict parsing and validation."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://www.searchapi.io/api/v1/search",
        http_client: Any = None,
        timeout: float = 10.0,
    ) -> None:
        if not isinstance(api_key, str) or api_key.strip() == "":
            raise ValueError("SearchApiExchangeProvider requires a non-empty api_key")

        self._api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self._http_client = http_client if http_client is not None else self._build_default_client()

    def _build_default_client(self) -> Any:
        try:
            import httpx  # type: ignore
        except Exception as exc:
            raise ExchangeProviderError("HTTP client unavailable for exchange provider") from exc
        return httpx.Client()

    def get_quote(self, base_currency: str, target_currency: str) -> dict[str, Any]:
        if not isinstance(base_currency, str) or base_currency.strip() == "":
            raise ExchangeProviderError("base_currency is required")
        if not isinstance(target_currency, str) or target_currency.strip() == "":
            raise ExchangeProviderError("target_currency is required")

        base = base_currency.strip().upper()
        target = target_currency.strip().upper()

        params = {
            "engine": "google",
            "q": f"{base} to {target} exchange rate",
            "api_key": self._api_key,
        }

        try:
            response = self._http_client.get(
                self.base_url,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise ExchangeProviderError("Exchange provider request failed") from exc

        try:
            answer_box = data["answer_box"]

            # SearchApi currency converter payload generally exposes the rate as
            # answer_box.price when answer_box.type == "currency_converter".
            if isinstance(answer_box, dict) and "price" in answer_box:
                rate_raw = answer_box["price"]
            else:
                # Backward-compatible fallback if a nested shape appears.
                converter = answer_box["currency_converter"]
                rate_raw = converter["exchange_rate"]

            rate = float(rate_raw)
        except Exception as exc:
            raise ExchangeProviderError("Exchange provider returned malformed response") from exc

        if rate <= 0:
            raise ExchangeProviderError("Exchange provider returned non-positive rate")

        return {
            "base_currency": base,
            "target_currency": target,
            "rate": rate,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provider": "searchapi",
        }