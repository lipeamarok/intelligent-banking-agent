"""Unit tests for exchange provider contract layer."""

import inspect

from app.exchange.provider import ExchangeProvider, ExchangeProviderError


def test_exchange_provider_error_exists_and_is_exception():
    assert issubclass(ExchangeProviderError, Exception)


def test_exchange_provider_defines_get_quote():
    assert hasattr(ExchangeProvider, "get_quote")


def test_provider_module_does_not_import_forbidden_sdks_or_network_libs():
    import app.exchange.provider as mod

    source_file = inspect.getfile(mod)
    with open(source_file, encoding="utf-8") as f:
        source = f.read()

    for forbidden in (
        "import requests",
        "import httpx",
        "import openai",
        "import grok",
        "import langchain",
    ):
        assert forbidden not in source


def test_provider_module_does_not_read_dotenv():
    import app.exchange.provider as mod

    source_file = inspect.getfile(mod)
    with open(source_file, encoding="utf-8") as f:
        source = f.read()

    assert "dotenv" not in source
    assert "load_dotenv" not in source
