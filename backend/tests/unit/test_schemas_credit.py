"""
Unit tests for app/schemas/credit.py
"""

import pytest
from pydantic import ValidationError

from app.schemas.credit import (
    CreditInterviewData,
    CreditLimitRequest,
    CreditRequestStatus,
    EmploymentType,
)


# ── CreditLimitRequest ────────────────────────────────────────────────────────


def test_credit_limit_request_zero_novo_limite_fails():
    with pytest.raises(ValidationError):
        CreditLimitRequest(
            cpf_cliente="12345678901",
            limite_atual=1000.0,
            novo_limite_solicitado=0,
        )


def test_credit_limit_request_negative_novo_limite_fails():
    with pytest.raises(ValidationError):
        CreditLimitRequest(
            cpf_cliente="12345678901",
            limite_atual=1000.0,
            novo_limite_solicitado=-500.0,
        )


def test_credit_limit_request_above_max_fails():
    with pytest.raises(ValidationError):
        CreditLimitRequest(
            cpf_cliente="12345678901",
            limite_atual=1000.0,
            novo_limite_solicitado=1_000_001.0,
        )


def test_credit_limit_request_at_max_passes():
    req = CreditLimitRequest(
        cpf_cliente="12345678901",
        limite_atual=1000.0,
        novo_limite_solicitado=1_000_000.0,
    )
    assert req.novo_limite_solicitado == 1_000_000.0


def test_credit_limit_request_default_status_is_pendente():
    req = CreditLimitRequest(
        cpf_cliente="12345678901",
        limite_atual=1000.0,
        novo_limite_solicitado=5000.0,
    )
    assert req.status_pedido == CreditRequestStatus.PENDENTE


def test_credit_limit_request_negative_limite_atual_fails():
    with pytest.raises(ValidationError):
        CreditLimitRequest(
            cpf_cliente="12345678901",
            limite_atual=-100.0,
            novo_limite_solicitado=5000.0,
        )


# ── CreditInterviewData ───────────────────────────────────────────────────────


def test_credit_interview_data_valid_passes():
    data = CreditInterviewData(
        renda_mensal=5000.0,
        tipo_emprego=EmploymentType.FORMAL,
        despesas_fixas_mensais=1500.0,
        numero_dependentes=2,
        tem_dividas_ativas=False,
    )
    assert data.renda_mensal == 5000.0
    assert data.tipo_emprego == EmploymentType.FORMAL


def test_credit_interview_data_negative_renda_fails():
    with pytest.raises(ValidationError):
        CreditInterviewData(
            renda_mensal=-1.0,
            tipo_emprego=EmploymentType.FORMAL,
            despesas_fixas_mensais=0.0,
            numero_dependentes=0,
            tem_dividas_ativas=False,
        )


def test_credit_interview_data_negative_dependents_fails():
    with pytest.raises(ValidationError):
        CreditInterviewData(
            renda_mensal=3000.0,
            tipo_emprego=EmploymentType.AUTONOMO,
            despesas_fixas_mensais=500.0,
            numero_dependentes=-1,
            tem_dividas_ativas=False,
        )


def test_credit_interview_data_zero_renda_passes():
    data = CreditInterviewData(
        renda_mensal=0.0,
        tipo_emprego=EmploymentType.DESEMPREGADO,
        despesas_fixas_mensais=0.0,
        numero_dependentes=0,
        tem_dividas_ativas=True,
    )
    assert data.renda_mensal == 0.0


def test_credit_interview_data_canonical_field_names():
    """All canonical field names from PROJECT.md must be present on the model."""
    data = CreditInterviewData(
        renda_mensal=2000.0,
        tipo_emprego=EmploymentType.AUTONOMO,
        despesas_fixas_mensais=800.0,
        numero_dependentes=1,
        tem_dividas_ativas=True,
    )
    assert hasattr(data, "renda_mensal")
    assert hasattr(data, "tipo_emprego")
    assert hasattr(data, "despesas_fixas_mensais")
    assert hasattr(data, "numero_dependentes")
    assert hasattr(data, "tem_dividas_ativas")
