"""Centralized environment-based settings for application bootstrap."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    """Bootstrap/runtime settings loaded from process environment."""

    app_env: str = "local"
    data_dir: str = "app/data"

    xai_api_key: str | None = None
    openai_api_key: str | None = None
    exchange_api_key: str | None = None

    xai_url: str = "https://api.x.ai/v1/chat/completions"
    openai_url: str = "https://api.openai.com/v1/chat/completions"
    primary_model: str = "grok-4-1-fast"
    fallback_model: str = "gpt-5.1"

    exchange_provider: str = "searchapi"
    exchange_base_url: str = "https://www.searchapi.io/api/v1/search"

    admin_enabled: bool = False

    def safe_summary(self) -> dict[str, object]:
        """Return a non-sensitive summary suitable for logs and smoke output."""
        return {
            "app_env": self.app_env,
            "data_dir": self.data_dir,
            "xai_configured": bool(self.xai_api_key),
            "openai_configured": bool(self.openai_api_key),
            "exchange_configured": bool(self.exchange_api_key),
            "primary_model": self.primary_model,
            "fallback_model": self.fallback_model,
            "exchange_provider": self.exchange_provider,
        }


def load_local_env_file(env_file: Path | None = None, *, override: bool = False) -> bool:
    """Load backend/.env into process environment for local runtime only.

    This helper is intentionally lightweight (stdlib-only) and does not print
    secret values. Existing env vars are preserved by default.
    """
    target = env_file or (Path(__file__).resolve().parents[2] / ".env")
    if not target.exists() or not target.is_file():
        return False

    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and (
            (value[0] == '"' and value[-1] == '"')
            or (value[0] == "'" and value[-1] == "'")
        ):
            value = value[1:-1]

        current = os.environ.get(key)
        should_set = override or (current is None) or (current == "")
        if should_set:
            os.environ[key] = value

    return True


def load_settings_from_env() -> Settings:
    """Load settings from process environment (including local backend/.env)."""
    env_override = os.environ.get("BANKING_AI_AGENT_DOTENV_PATH")
    load_local_env_file(Path(env_override) if env_override else None)

    exchange_provider = os.environ.get("EXCHANGE_PROVIDER", "searchapi").strip().lower()

    return Settings(
        app_env=os.environ.get("APP_ENV", "local"),
        data_dir=os.environ.get("DATA_DIR", "app/data"),
        xai_api_key=os.environ.get("XAI_API_KEY"),
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        exchange_api_key=os.environ.get("EXCHANGE_API_KEY"),
        xai_url=os.environ.get("XAI_URL", "https://api.x.ai/v1/chat/completions"),
        openai_url=os.environ.get("OPENAI_URL", "https://api.openai.com/v1/chat/completions"),
        primary_model=os.environ.get("PRIMARY_MODEL", "grok-4-1-fast"),
        fallback_model=os.environ.get("FALLBACK_MODEL", "gpt-5.1"),
        exchange_provider=exchange_provider or "searchapi",
        exchange_base_url=os.environ.get("EXCHANGE_BASE_URL", "https://www.searchapi.io/api/v1/search"),
        admin_enabled=os.environ.get("ADMIN_ENABLED", "").strip().lower() in ("true", "1", "yes")
            or os.environ.get("APP_ENV", "local") == "local",
    )
