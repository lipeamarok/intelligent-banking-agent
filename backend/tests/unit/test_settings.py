"""Unit tests for centralized Settings loading and safe summary behavior."""

from pathlib import Path

from app.api import dependencies as api_dependencies
from app.config.settings import Settings, load_settings_from_env


def test_load_settings_from_env_uses_defaults_when_env_missing(monkeypatch):
    keys = [
        "APP_ENV",
        "DATA_DIR",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "EXCHANGE_API_KEY",
        "XAI_URL",
        "OPENAI_URL",
        "PRIMARY_MODEL",
        "FALLBACK_MODEL",
        "EXCHANGE_PROVIDER",
        "EXCHANGE_BASE_URL",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("BANKING_AI_AGENT_DOTENV_PATH", "__missing_dotenv_for_test__.env")

    settings = load_settings_from_env()

    assert settings.app_env == "local"
    assert settings.data_dir == "app/data"
    assert settings.xai_api_key is None
    assert settings.openai_api_key is None
    assert settings.exchange_api_key is None
    assert settings.exchange_provider == "searchapi"
    assert settings.exchange_base_url == "https://www.searchapi.io/api/v1/search"


def test_load_settings_from_env_reads_expected_variables(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATA_DIR", "custom/data")
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test")
    monkeypatch.setenv("EXCHANGE_API_KEY", "exchange-test")
    monkeypatch.setenv("XAI_URL", "https://xai.example/v1/chat")
    monkeypatch.setenv("OPENAI_URL", "https://openai.example/v1/chat")
    monkeypatch.setenv("PRIMARY_MODEL", "grok-test")
    monkeypatch.setenv("FALLBACK_MODEL", "gpt-test")
    monkeypatch.setenv("EXCHANGE_PROVIDER", "serpapi")
    monkeypatch.setenv("EXCHANGE_BASE_URL", "https://provider.example/search")

    settings = load_settings_from_env()

    assert settings.app_env == "test"
    assert settings.data_dir == "custom/data"
    assert settings.xai_api_key == "xai-test"
    assert settings.openai_api_key == "openai-test"
    assert settings.exchange_api_key == "exchange-test"
    assert settings.xai_url == "https://xai.example/v1/chat"
    assert settings.openai_url == "https://openai.example/v1/chat"
    assert settings.primary_model == "grok-test"
    assert settings.fallback_model == "gpt-test"
    assert settings.exchange_provider == "serpapi"
    assert settings.exchange_base_url == "https://provider.example/search"


def test_load_settings_normalizes_exchange_provider(monkeypatch):
    monkeypatch.setenv("EXCHANGE_PROVIDER", "SearchApi")
    settings = load_settings_from_env()
    assert settings.exchange_provider == "searchapi"


def test_settings_safe_summary_does_not_include_secret_values():
    settings = Settings(
        xai_api_key="xai-secret",
        openai_api_key="openai-secret",
        exchange_api_key="exchange-secret",
    )

    summary = settings.safe_summary()

    assert "xai_api_key" not in summary
    assert "openai_api_key" not in summary
    assert "exchange_api_key" not in summary

    assert summary["xai_configured"] is True
    assert summary["openai_configured"] is True
    assert summary["exchange_configured"] is True

    assert "xai-secret" not in str(summary)
    assert "openai-secret" not in str(summary)
    assert "exchange-secret" not in str(summary)


def test_settings_does_not_print_secrets(monkeypatch, capsys):
    monkeypatch.setenv("XAI_API_KEY", "xai-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("EXCHANGE_API_KEY", "exchange-secret")

    _ = load_settings_from_env()

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_env_example_contains_required_placeholders():
    env_example = Path(__file__).resolve().parents[2] / ".env.example"
    content = env_example.read_text(encoding="utf-8")

    assert "XAI_API_KEY=" in content
    assert "OPENAI_API_KEY=" in content
    assert "EXCHANGE_API_KEY=" in content
    assert "EXCHANGE_PROVIDER=" in content
    assert "EXCHANGE_BASE_URL=" in content

    lines = content.splitlines()
    assert not any(line.strip().startswith("GROK_API_KEY=") for line in lines)


def test_load_settings_from_env_loads_dotenv_before_settings_creation(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "APP_ENV=test-local\n"
        "DATA_DIR=tmp/data\n"
        "XAI_API_KEY=xai-from-dotenv\n"
        "OPENAI_API_KEY=openai-from-dotenv\n"
        "EXCHANGE_API_KEY=exchange-from-dotenv\n"
        "XAI_URL=https://xai.dotenv/v1/chat\n"
        "OPENAI_URL=https://openai.dotenv/v1/chat\n"
        "PRIMARY_MODEL=grok-dotenv\n"
        "FALLBACK_MODEL=gpt-dotenv\n"
        "EXCHANGE_PROVIDER=searchapi\n"
        "EXCHANGE_BASE_URL=https://exchange.dotenv/search\n",
        encoding="utf-8",
    )

    for key in (
        "APP_ENV",
        "DATA_DIR",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "EXCHANGE_API_KEY",
        "XAI_URL",
        "OPENAI_URL",
        "PRIMARY_MODEL",
        "FALLBACK_MODEL",
        "EXCHANGE_PROVIDER",
        "EXCHANGE_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("BANKING_AI_AGENT_DOTENV_PATH", str(dotenv))

    settings = load_settings_from_env()
    summary = settings.safe_summary()

    assert settings.app_env == "test-local"
    assert settings.data_dir == "tmp/data"
    assert summary["xai_configured"] is True
    assert summary["openai_configured"] is True
    assert summary["exchange_configured"] is True


def test_get_settings_uses_dotenv_loaded_values(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "APP_ENV=test-cache\n"
        "DATA_DIR=tmp/cache\n"
        "XAI_API_KEY=xai-cache\n"
        "OPENAI_API_KEY=openai-cache\n"
        "EXCHANGE_API_KEY=exchange-cache\n",
        encoding="utf-8",
    )

    for key in (
        "APP_ENV",
        "DATA_DIR",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "EXCHANGE_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("BANKING_AI_AGENT_DOTENV_PATH", str(dotenv))

    api_dependencies.clear_api_dependency_caches()
    settings = api_dependencies.get_settings()
    summary = settings.safe_summary()

    assert settings.app_env == "test-cache"
    assert settings.data_dir == "tmp/cache"
    assert summary["xai_configured"] is True
    assert summary["openai_configured"] is True
    assert summary["exchange_configured"] is True


def test_load_settings_from_env_backfills_empty_env_values(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "XAI_API_KEY=xai-dotenv\n"
        "OPENAI_API_KEY=openai-dotenv\n"
        "EXCHANGE_API_KEY=exchange-dotenv\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("BANKING_AI_AGENT_DOTENV_PATH", str(dotenv))
    monkeypatch.setenv("XAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("EXCHANGE_API_KEY", "")

    settings = load_settings_from_env()

    assert settings.xai_api_key == "xai-dotenv"
    assert settings.openai_api_key == "openai-dotenv"
    assert settings.exchange_api_key == "exchange-dotenv"
