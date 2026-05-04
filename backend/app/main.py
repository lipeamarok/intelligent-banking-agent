"""FastAPI application assembly for Banco Agil backend API."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import admin, chat, health, sessions
from app.config.settings import load_local_env_file, load_settings_from_env
from scripts.seed_data import seed_runtime_data
from app.observability.logger import get_logger, log_event
from app.schemas.common import SuggestedAction
from app.schemas.errors import ErrorCode, ErrorDetail, ErrorResponse

logger = get_logger(__name__)


def _resolve_trace_id(request: Request) -> str:
    trace_id = request.headers.get("x-trace-id")
    if not trace_id:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(trace_id))
    except (TypeError, ValueError):
        return str(uuid.uuid4())


def _build_error_response(
    *,
    code: ErrorCode,
    message: str,
    trace_id: str,
    recoverable: bool,
    suggested_action: SuggestedAction,
) -> dict[str, object]:
    return ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            trace_id=trace_id,
            recoverable=recoverable,
            suggested_action=suggested_action,
        )
    ).model_dump()


def create_app() -> FastAPI:
    """Create FastAPI app, middleware, routers and error handlers."""
    # Local convenience: auto-load backend/.env when present.
    load_local_env_file()

    # Ensure dependency caches are rebuilt with the effective runtime env.
    from app.api import dependencies as api_dependencies

    api_dependencies.clear_api_dependency_caches()

    settings = load_settings_from_env()
    backend_root = Path(__file__).resolve().parents[1]
    data_dir = Path(settings.data_dir)
    if not data_dir.is_absolute():
        data_dir = (backend_root / data_dir).resolve()

    # Reset CSV data to known seed state on every startup so smoke tests
    # and manual UI exploration never contaminate each other.
    seed_runtime_data(data_dir=data_dir, reset=True)
    log_event(
        logger,
        "startup_runtime",
        pid=os.getpid(),
        python=sys.executable,
        cwd=str(Path.cwd()),
        backend_root=str(backend_root),
        data_dir=str(data_dir),
        app_env=settings.app_env,
        xai_configured=bool(settings.xai_api_key),
        openai_configured=bool(settings.openai_api_key),
        exchange_configured=bool(settings.exchange_api_key),
        exchange_provider=settings.exchange_provider,
        data_dir_exists=data_dir.exists() and data_dir.is_dir(),
        clientes_csv_exists=(data_dir / "clientes.csv").exists(),
        score_limite_csv_exists=(data_dir / "score_limite.csv").exists(),
        solicitacoes_csv_exists=(data_dir / "solicitacoes_aumento_limite.csv").exists(),
    )

    app = FastAPI(
        title="Banco Agil API",
        version=os.environ.get("APP_VERSION", "1.0.0"),
        description="Intelligent Banking Agent API",
    )

    cors_origins_raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
    cors_origins = [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(sessions.router)
    app.include_router(admin.router)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, _exc: RequestValidationError):
        trace_id = _resolve_trace_id(request)
        return JSONResponse(
            status_code=422,
            content=_build_error_response(
                code=ErrorCode.VALIDATION_ERROR,
                message="Request validation failed",
                trace_id=trace_id,
                recoverable=True,
                suggested_action=SuggestedAction.RETRY,
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)

        trace_id = _resolve_trace_id(request)
        return JSONResponse(
            status_code=exc.status_code,
            content=_build_error_response(
                code=ErrorCode.INTERNAL_ERROR,
                message="Request failed",
                trace_id=trace_id,
                recoverable=True,
                suggested_action=SuggestedAction.RETRY,
            ),
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, _exc: Exception):
        trace_id = _resolve_trace_id(request)
        return JSONResponse(
            status_code=500,
            content=_build_error_response(
                code=ErrorCode.INTERNAL_ERROR,
                message="Internal server error",
                trace_id=trace_id,
                recoverable=True,
                suggested_action=SuggestedAction.RETRY,
            ),
        )

    return app


app = create_app()
