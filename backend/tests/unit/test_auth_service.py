"""
Unit tests for AuthService.

Source of truth: REQUIREMENTS.md FR-AUTH-001–006, TEST_PLAN.md section 6.3.

Uses FakeCustomerRepository — no CSV files, no network, no real data.
"""

import pytest

from app.services.auth_service import AuthResult, AuthService
from tests.conftest import ANA, CARLOS, MARINA, FakeCustomerRepository


# ── Successful authentication ──────────────────────────────────────────────────


def test_auth_service_authenticates_valid_customer():
    """TC-AUTH-001: valid CPF + birth date → success=True, customer returned."""
    repo = FakeCustomerRepository([ANA, CARLOS, MARINA])
    result = AuthService.authenticate("12345678901", "1990-05-12", repo)
    assert isinstance(result, AuthResult)
    assert result.success is True
    assert result.customer is not None
    assert result.customer.cpf == "12345678901"
    assert result.customer.nome == "Ana Silva"


def test_auth_service_returns_correct_customer_object():
    """Returned Customer must match the repository record exactly."""
    repo = FakeCustomerRepository([ANA, CARLOS, MARINA])
    result = AuthService.authenticate("98765432100", "1985-11-20", repo)
    assert result.success is True
    assert result.customer.score_atual == 540
    assert result.customer.limite_credito == 2500.00


# ── Failed authentication ──────────────────────────────────────────────────────


def test_auth_service_rejects_unknown_cpf():
    """TC-AUTH-002: CPF not in repository → success=False."""
    repo = FakeCustomerRepository([ANA, CARLOS, MARINA])
    result = AuthService.authenticate("00000000000", "1990-01-01", repo)
    assert result.success is False
    assert result.customer is None


def test_auth_service_rejects_wrong_birth_date():
    """TC-AUTH-003: CPF exists but birth date does not match → success=False."""
    repo = FakeCustomerRepository([ANA, CARLOS, MARINA])
    result = AuthService.authenticate("12345678901", "1999-12-31", repo)
    assert result.success is False
    assert result.customer is None


def test_auth_service_failure_has_reason():
    """AuthResult for failures must include a failure_reason."""
    repo = FakeCustomerRepository([ANA])
    result = AuthService.authenticate("99999999999", "2000-01-01", repo)
    assert result.success is False
    assert result.failure_reason is not None
    assert isinstance(result.failure_reason, str)


# ── CPF string preservation ────────────────────────────────────────────────────


def test_auth_service_preserves_cpf_as_string():
    """TC-AUTH-004: CPF must always be treated as string, never as integer."""
    customer_with_leading_zero = ANA.model_copy(update={"cpf": "01234567890"})
    repo = FakeCustomerRepository([customer_with_leading_zero])
    result = AuthService.authenticate("01234567890", "1990-05-12", repo)
    assert result.success is True
    assert isinstance(result.customer.cpf, str)
    assert result.customer.cpf == "01234567890"


def test_auth_service_cpf_with_leading_zero_does_not_match_as_integer():
    """
    CPF "01234567890" stored as string must NOT match "1234567890" (integer form).
    If CPF were converted to int, leading zero would be lost and cause false match.
    """
    customer_with_leading_zero = ANA.model_copy(update={"cpf": "01234567890"})
    repo = FakeCustomerRepository([customer_with_leading_zero])
    result = AuthService.authenticate("1234567890", "1990-05-12", repo)
    assert result.success is False


# ── Service isolation ──────────────────────────────────────────────────────────


def test_auth_service_does_not_own_attempt_counting():
    """
    AuthService must return a result per attempt without tracking count.
    Attempt counting and session blocking belong to the graph node (triage_node).
    This test confirms AuthService returns a valid AuthResult every time
    it is called, regardless of previous calls.
    """
    repo = FakeCustomerRepository([ANA])
    for _ in range(5):
        result = AuthService.authenticate("99999999999", "2000-01-01", repo)
        assert result.success is False
        # No exception, no internal counter — just a clean result each time


def test_auth_service_result_contains_no_ui_message():
    """
    AuthResult must not contain user-facing UI message strings.
    UI messaging is the responsibility of the LLM-assisted agent layer.
    """
    repo = FakeCustomerRepository([ANA])
    result = AuthService.authenticate("12345678901", "1990-05-12", repo)
    assert not hasattr(result, "message")
    assert not hasattr(result, "reply")
    assert not hasattr(result, "display_text")
