"""
Unit tests for CreditService.

Source of truth: REQUIREMENTS.md FR-CREDIT-001–006, TEST_PLAN.md section 6.5.

Uses FakeScoreLimitRepository and FakeCreditRequestRepository.
No CSV files, no network access.
"""

import pytest

from app.schemas.credit import CreditLimitRequest, CreditRequestStatus
from app.services.credit_service import CreditResult, CreditService
from tests.conftest import (
    ANA,       # score=720, limite_credito=5000.00 → max_limit=10000.00
    CARLOS,    # score=540, limite_credito=2500.00 → max_limit=5000.00
    MARINA,    # score=250, limite_credito=800.00  → max_limit=1000.00
    FakeScoreLimitRepository,
    FakeCreditRequestRepository,
)


# ── get_current_limit (TC-CREDIT-001) ─────────────────────────────────────────


def test_credit_service_returns_current_limit():
    """TC-CREDIT-001: current limit returned from authenticated customer object."""
    limit = CreditService.get_current_limit(ANA)
    assert limit == 5000.00


def test_credit_service_current_limit_is_float():
    limit = CreditService.get_current_limit(CARLOS)
    assert isinstance(limit, float)


def test_credit_service_current_limit_different_customers():
    assert CreditService.get_current_limit(ANA) != CreditService.get_current_limit(MARINA)


# ── evaluate_limit_request — approval (TC-CREDIT-002) ────────────────────────


def test_credit_service_approves_request_within_allowed_limit():
    """
    TC-CREDIT-002: ANA score=720 → max_limit=10000.
    Requesting 8000 must be approved.
    """
    request = CreditLimitRequest(
        cpf_cliente=ANA.cpf,
        limite_atual=ANA.limite_credito,
        novo_limite_solicitado=8000.0,
    )
    score_repo = FakeScoreLimitRepository()
    request_repo = FakeCreditRequestRepository()

    result = CreditService.evaluate_limit_request(request, ANA, score_repo, request_repo)

    assert isinstance(result, CreditResult)
    assert result.approved is True
    assert result.request.status_pedido == CreditRequestStatus.APROVADO


def test_credit_service_approves_request_exactly_at_max_limit():
    """Request equal to max allowed limit must be approved."""
    request = CreditLimitRequest(
        cpf_cliente=ANA.cpf,
        limite_atual=ANA.limite_credito,
        novo_limite_solicitado=10000.0,  # exactly the max for score=720
    )
    score_repo = FakeScoreLimitRepository()
    request_repo = FakeCreditRequestRepository()

    result = CreditService.evaluate_limit_request(request, ANA, score_repo, request_repo)

    assert result.approved is True


# ── evaluate_limit_request — rejection (TC-CREDIT-003) ───────────────────────


def test_credit_service_rejects_request_above_allowed_limit():
    """
    TC-CREDIT-003: CARLOS score=540 → max_limit=5000.
    Requesting 8000 must be rejected.
    """
    request = CreditLimitRequest(
        cpf_cliente=CARLOS.cpf,
        limite_atual=CARLOS.limite_credito,
        novo_limite_solicitado=8000.0,
    )
    score_repo = FakeScoreLimitRepository()
    request_repo = FakeCreditRequestRepository()

    result = CreditService.evaluate_limit_request(request, CARLOS, score_repo, request_repo)

    assert result.approved is False
    assert result.request.status_pedido == CreditRequestStatus.REJEITADO


def test_credit_service_rejects_request_just_above_max():
    """Request one unit above allowed limit must be rejected."""
    request = CreditLimitRequest(
        cpf_cliente=CARLOS.cpf,
        limite_atual=CARLOS.limite_credito,
        novo_limite_solicitado=5001.0,  # max is 5000 for score=540
    )
    score_repo = FakeScoreLimitRepository()
    request_repo = FakeCreditRequestRepository()

    result = CreditService.evaluate_limit_request(request, CARLOS, score_repo, request_repo)

    assert result.approved is False


# ── Persistence (TC-CREDIT-005) ───────────────────────────────────────────────


def test_credit_service_persists_approved_request():
    """TC-CREDIT-005: approved request must be appended via credit_request_repo."""
    request = CreditLimitRequest(
        cpf_cliente=ANA.cpf,
        limite_atual=ANA.limite_credito,
        novo_limite_solicitado=8000.0,
    )
    score_repo = FakeScoreLimitRepository()
    request_repo = FakeCreditRequestRepository()

    CreditService.evaluate_limit_request(request, ANA, score_repo, request_repo)

    assert len(request_repo.appended) == 1
    assert request_repo.appended[0].cpf_cliente == ANA.cpf


def test_credit_service_persists_rejected_request():
    """Rejected requests must also be persisted."""
    request = CreditLimitRequest(
        cpf_cliente=CARLOS.cpf,
        limite_atual=CARLOS.limite_credito,
        novo_limite_solicitado=8000.0,
    )
    score_repo = FakeScoreLimitRepository()
    request_repo = FakeCreditRequestRepository()

    CreditService.evaluate_limit_request(request, CARLOS, score_repo, request_repo)

    assert len(request_repo.appended) == 1
    assert request_repo.appended[0].status_pedido != CreditRequestStatus.PENDENTE


def test_credit_service_does_not_leave_status_as_pendente():
    """Every evaluated request must have final status: aprovado or rejeitado."""
    request = CreditLimitRequest(
        cpf_cliente=ANA.cpf,
        limite_atual=ANA.limite_credito,
        novo_limite_solicitado=8000.0,
    )
    score_repo = FakeScoreLimitRepository()
    request_repo = FakeCreditRequestRepository()

    result = CreditService.evaluate_limit_request(request, ANA, score_repo, request_repo)

    assert result.request.status_pedido != CreditRequestStatus.PENDENTE


# ── Decision rationale (TC-CREDIT-006) ───────────────────────────────────────


def test_credit_service_returns_rationale():
    """TC-CREDIT-006: result must contain rationale with score/limit context."""
    request = CreditLimitRequest(
        cpf_cliente=ANA.cpf,
        limite_atual=ANA.limite_credito,
        novo_limite_solicitado=8000.0,
    )
    score_repo = FakeScoreLimitRepository()
    request_repo = FakeCreditRequestRepository()

    result = CreditService.evaluate_limit_request(request, ANA, score_repo, request_repo)

    assert isinstance(result.rationale, str)
    assert len(result.rationale) > 0


# ── Service isolation ─────────────────────────────────────────────────────────


def test_credit_service_does_not_calculate_score():
    """
    CreditService reads score from Customer.score_atual.
    It must not recalculate it. Changing score in the customer object must
    immediately change the approval decision.
    """
    low_score_ana = ANA.model_copy(update={"score_atual": 250})  # max_limit=1000
    request = CreditLimitRequest(
        cpf_cliente=low_score_ana.cpf,
        limite_atual=low_score_ana.limite_credito,
        novo_limite_solicitado=5000.0,  # above max for score=250
    )
    score_repo = FakeScoreLimitRepository()
    request_repo = FakeCreditRequestRepository()

    result = CreditService.evaluate_limit_request(
        request, low_score_ana, score_repo, request_repo
    )
    assert result.approved is False


def test_credit_service_does_not_authenticate_customer():
    """
    CreditService accepts any Customer object.
    Authentication must have been verified before reaching this service.
    Service must not perform its own authentication check.
    """
    # Passing a customer with no CPF match in repo should still work
    # because CreditService doesn't check authentication — it trusts input
    request = CreditLimitRequest(
        cpf_cliente=MARINA.cpf,
        limite_atual=MARINA.limite_credito,
        novo_limite_solicitado=500.0,  # within max_limit=1000 for score=250
    )
    score_repo = FakeScoreLimitRepository()
    request_repo = FakeCreditRequestRepository()

    result = CreditService.evaluate_limit_request(request, MARINA, score_repo, request_repo)
    assert result.approved is True
