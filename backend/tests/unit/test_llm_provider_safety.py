"""Safety checks for HTTP-based providers (no real network, no SDK lock-in)."""

import inspect
from pathlib import Path


def test_no_real_network_in_provider_tests():
    import tests.unit.test_grok_provider as grok_tests
    import tests.unit.test_openai_provider as openai_tests

    assert hasattr(grok_tests, "FakeHTTPClient")
    assert hasattr(openai_tests, "FakeHTTPClient")


def test_providers_do_not_import_openai_or_xai_sdks():
    import app.llm.grok_provider as grok_provider
    import app.llm.openai_provider as openai_provider

    for module in (grok_provider, openai_provider):
        source_file = inspect.getfile(module)
        with open(source_file, encoding="utf-8") as f:
            source = f.read()
        assert "import openai" not in source
        assert "import xai" not in source
        assert "import langchain" not in source


def test_providers_do_not_read_dotenv_directly():
    import app.llm.grok_provider as grok_provider
    import app.llm.openai_provider as openai_provider

    for module in (grok_provider, openai_provider):
        source_file = inspect.getfile(module)
        with open(source_file, encoding="utf-8") as f:
            source = f.read()
        assert "dotenv" not in source
        assert "load_dotenv" not in source


def test_env_example_uses_canonical_llm_key_names_and_placeholders():
    env_example = Path(__file__).resolve().parents[2] / ".env.example"
    content = env_example.read_text(encoding="utf-8")

    assert "XAI_API_KEY=" in content
    assert "OPENAI_API_KEY=" in content
    assert "EXCHANGE_API_KEY=" in content
    assert "XAI_URL=https://api.x.ai/v1/chat/completions" in content
    assert "OPENAI_URL=https://api.openai.com/v1/chat/completions" in content
    assert "PRIMARY_MODEL=grok-4-1-fast" in content
    assert "FALLBACK_MODEL=gpt-5.1" in content
    assert "\nGROK_API_KEY=" not in content


def test_env_example_does_not_contain_obvious_real_secret_values():
    env_example = Path(__file__).resolve().parents[2] / ".env.example"
    content = env_example.read_text(encoding="utf-8")

    for forbidden_prefix in ("xai-", "sk-"):
        assert forbidden_prefix not in content
