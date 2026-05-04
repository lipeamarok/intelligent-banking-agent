"""GET /api/v1/health endpoint implementation."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.dependencies import get_trace_id
from app.schemas.health import HealthResponse, HealthStatus

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check(trace_id: str = Depends(get_trace_id)) -> HealthResponse:
    """Return API process health without calling external providers."""
    return HealthResponse(
        status=HealthStatus.OK,
        version=os.environ.get("APP_VERSION", "1.0.0"),
        timestamp=datetime.now(timezone.utc).isoformat(),
        trace_id=trace_id,
        dependencies={"api": "ok"},
    )
