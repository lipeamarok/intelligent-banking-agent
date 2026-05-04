"""
Unit tests for app/schemas/errors.py
"""

import pytest
from pydantic import ValidationError

from app.schemas.common import SuggestedAction
from app.schemas.errors import ErrorCode, ErrorDetail, ErrorResponse


def test_error_response_follows_envelope():
    """Error responses must follow the { "error": { ... } } envelope."""
    detail = ErrorDetail(
        code=ErrorCode.INTERNAL_ERROR,
        message="Ocorreu um erro inesperado.",
        trace_id="trace-001",
    )
    resp = ErrorResponse(error=detail)
    assert resp.error is not None
    assert resp.error.code == ErrorCode.INTERNAL_ERROR


def test_error_response_has_no_top_level_error_code():
    """ErrorResponse must not expose error_code at the root level."""
    detail = ErrorDetail(
        code=ErrorCode.VALIDATION_ERROR,
        message="Campo inválido.",
        trace_id="trace-002",
    )
    resp = ErrorResponse(error=detail)
    assert not hasattr(resp, "error_code"), (
        "error_code must not exist at the root level of ErrorResponse"
    )


def test_error_code_corrupted_data_file_exists():
    assert ErrorCode.CORRUPTED_DATA_FILE is not None
    assert ErrorCode.CORRUPTED_DATA_FILE.value == "CORRUPTED_DATA_FILE"


def test_error_detail_recoverable_default_true():
    detail = ErrorDetail(
        code=ErrorCode.SESSION_NOT_FOUND,
        message="Sessão não encontrada.",
        trace_id="trace-003",
    )
    assert detail.recoverable is True


def test_error_detail_suggested_action_default_none():
    detail = ErrorDetail(
        code=ErrorCode.AUTH_FAILED,
        message="Autenticação falhou.",
        trace_id="trace-004",
    )
    assert detail.suggested_action == SuggestedAction.NONE


def test_error_detail_non_recoverable():
    detail = ErrorDetail(
        code=ErrorCode.AUTH_BLOCKED,
        message="Sessão bloqueada por excesso de tentativas.",
        trace_id="trace-005",
        recoverable=False,
        suggested_action=SuggestedAction.RESET,
    )
    assert detail.recoverable is False
    assert detail.suggested_action == SuggestedAction.RESET


def test_all_error_codes_defined():
    """All error codes from API_CONTRACT.md must be present in ErrorCode."""
    expected = {
        "VALIDATION_ERROR",
        "SESSION_NOT_FOUND",
        "SESSION_EXPIRED",
        "AUTH_FAILED",
        "AUTH_BLOCKED",
        "STATE_TRANSITION_DENIED",
        "CSV_READ_ERROR",
        "CSV_WRITE_ERROR",
        "LOCK_TIMEOUT",
        "LLM_PROVIDER_ERROR",
        "EXCHANGE_PROVIDER_ERROR",
        "MISSING_DATA_FILE",
        "CORRUPTED_DATA_FILE",
        "INTERNAL_ERROR",
    }
    defined = {code.value for code in ErrorCode}
    assert expected.issubset(defined)
