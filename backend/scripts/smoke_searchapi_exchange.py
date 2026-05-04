"""Manual smoke test for SearchApiExchangeProvider (single real call)."""

from __future__ import annotations

import os

from app.exchange.searchapi_provider import SearchApiExchangeProvider


def main() -> int:
    api_key = os.getenv("EXCHANGE_API_KEY")
    if not api_key:
        print("EXCHANGE_API_KEY is not set")
        return 1

    provider = SearchApiExchangeProvider(api_key=api_key)
    quote = provider.get_quote("BRL", "USD")

    print(f"base_currency={quote.get('base_currency')}")
    print(f"target_currency={quote.get('target_currency')}")
    print(f"rate={quote.get('rate')}")
    print(f"provider={quote.get('provider')}")
    print(f"timestamp={quote.get('timestamp')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
