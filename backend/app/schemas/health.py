"""
Health check response schema.

Source of truth: API_CONTRACT.md section 7.
No endpoint implementation — schema only.
"""

from enum import Enum

from pydantic import BaseModel


class HealthStatus(str, Enum):
    """Overall system health classification."""

    OK = "ok"
    DEGRADED = "degraded"


class HealthResponse(BaseModel):
    """Response body for GET /api/v1/health."""

    status: HealthStatus
    version: str
    timestamp: str
    trace_id: str
    dependencies: dict[str, str] | None = None
