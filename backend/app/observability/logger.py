"""Safe structured logging helpers for local/runtime diagnostics."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

_SECRET_PATTERNS = [
    re.compile(r"(?i)(xai_api_key|openai_api_key|exchange_api_key)\s*=\s*[^,\s]+"),
    re.compile(r"(?i)(xai_api_key|openai_api_key|exchange_api_key)\s*:\s*[^,\s]+"),
    re.compile(r"(?i)authorization\s*:\s*[^,\s]+"),
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{8,})\b"),
    re.compile(r"\b(xai-[A-Za-z0-9_\-]{8,})\b"),
]


def sanitize_text(value: object) -> str:
    """Return a sanitized string safe for logs."""
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def get_logger(name: str) -> logging.Logger:
    """Get module logger with sane default level for local runtime diagnostics."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emit one-line JSON event with sanitized fields."""
    payload = {"event": event}
    for key, value in fields.items():
        if isinstance(value, (dict, list, tuple)):
            payload[key] = sanitize_text(json.dumps(value, default=str))
        else:
            payload[key] = sanitize_text(value)
    logger.info(json.dumps(payload, ensure_ascii=True, default=str))
