"""
Error codes, error detail, and error response envelope.

Source of truth: API_CONTRACT.md section 5.3 and error envelope definition.
"""

from enum import Enum

from pydantic import BaseModel

from app.schemas.common import SuggestedAction


class ErrorCode(str, Enum):
    """Controlled error codes for API error responses and internal diagnostics."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    AUTH_FAILED = "AUTH_FAILED"
    AUTH_BLOCKED = "AUTH_BLOCKED"
    STATE_TRANSITION_DENIED = "STATE_TRANSITION_DENIED"
    CSV_READ_ERROR = "CSV_READ_ERROR"
    CSV_WRITE_ERROR = "CSV_WRITE_ERROR"
    LOCK_TIMEOUT = "LOCK_TIMEOUT"
    LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"
    EXCHANGE_PROVIDER_ERROR = "EXCHANGE_PROVIDER_ERROR"
    MISSING_DATA_FILE = "MISSING_DATA_FILE"
    CORRUPTED_DATA_FILE = "CORRUPTED_DATA_FILE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorDetail(BaseModel):
    """Detail object nested inside the error envelope."""

    code: ErrorCode
    message: str
    trace_id: str
    recoverable: bool = True
    suggested_action: SuggestedAction = SuggestedAction.NONE


class ErrorResponse(BaseModel):
    """
    Public error response envelope.

    All error responses follow the structure: { "error": { ... } }
    Technical details must not leak to the frontend.
    """

    error: ErrorDetail
