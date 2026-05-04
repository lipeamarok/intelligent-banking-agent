"""FastAPI dependency providers for API routers."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from functools import lru_cache

from fastapi import Request

from app.bootstrap.graph import create_application_graph
from app.config.settings import Settings, load_settings_from_env
from app.observability.logger import get_logger, log_event, sanitize_text
from app.services.session_service import SessionService

logger = get_logger(__name__)


class GraphUnavailableError(RuntimeError):
    """Raised when the application graph is unavailable for invocation."""

    def __init__(self, message: str = "Application graph unavailable", *, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason or message


class _UnavailableGraph:
    """Fallback graph object used when bootstrap cannot create real graph."""

    def __init__(self, reason: str = "Application graph unavailable") -> None:
        self.reason = reason

    def invoke(self, *_args, **_kwargs):
        raise GraphUnavailableError("Application graph unavailable", reason=self.reason)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache process environment settings."""
    return load_settings_from_env()


@lru_cache(maxsize=1)
def get_session_service() -> SessionService:
    """Provide singleton in-memory session manager for V1."""
    return SessionService()


@lru_cache(maxsize=1)
def get_app_graph():
    """
    Create compiled app graph from bootstrap factories.

    Returns a safe fallback object if required runtime secrets are missing.
    This prevents dependency-resolution crashes and keeps API errors controlled.
    """
    try:
        effective_settings = get_settings()
        resolved_data_dir = Path(effective_settings.data_dir)
        if not resolved_data_dir.is_absolute():
            backend_root = Path(__file__).resolve().parents[2]
            resolved_data_dir = (backend_root / resolved_data_dir).resolve()

        log_event(
            logger,
            "graph_creation_start",
            pid=os.getpid(),
            python=sys.executable,
            cwd=str(Path.cwd()),
            settings_data_dir=effective_settings.data_dir,
            resolved_data_dir=str(resolved_data_dir),
        )

        graph = create_application_graph(effective_settings)
        log_event(logger, "graph_creation_success", pid=os.getpid(), python=sys.executable)
        return graph
    except Exception as exc:
        reason = sanitize_text(f"{type(exc).__name__}: {exc}")
        log_event(
            logger,
            "graph_creation_failed",
            exception_type=type(exc).__name__,
            sanitized_reason=reason,
            pid=os.getpid(),
            python=sys.executable,
        )
        print(f"Application graph unavailable: {reason}", file=sys.stderr)
        return _UnavailableGraph(reason=reason)


def clear_api_dependency_caches() -> None:
    """Clear API dependency caches for deterministic tests and lifecycle resets."""
    get_settings.cache_clear()
    get_session_service.cache_clear()
    get_app_graph.cache_clear()


def get_trace_id(request: Request) -> str:
    """Return validated trace id from header or generate a new UUID v4."""
    trace_id = request.headers.get("x-trace-id")
    if not trace_id:
        return str(uuid.uuid4())

    try:
        return str(uuid.UUID(trace_id))
    except (ValueError, TypeError):
        return str(uuid.uuid4())
