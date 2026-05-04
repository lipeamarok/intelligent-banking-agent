"""
Credit domain schemas.

Source of truth: PROJECT.md (model names), REQUIREMENTS.md (business validation rules).
No score calculation, no approval/rejection logic, no LLM calls, no CSV access.
"""

from enum import Enum

from pydantic import BaseModel, Field


class CreditRequestStatus(str, Enum):
    """Lifecycle status of a credit limit increase request."""

    PENDENTE = "pendente"
    APROVADO = "aprovado"
    REJEITADO = "rejeitado"


class EmploymentType(str, Enum):
    """Customer employment classification for credit interview."""

    FORMAL = "formal"
    AUTONOMO = "autonomo"
    DESEMPREGADO = "desempregado"


class CreditLimitRequest(BaseModel):
    """
    Credit limit increase request record.

    Stores normalized data only. Business decision (approve/reject) is made
    by the CreditService, not this schema.
    """

    cpf_cliente: str
    data_hora_solicitacao: str | None = None
    limite_atual: float = Field(ge=0)
    novo_limite_solicitado: float = Field(gt=0, le=1_000_000)
    status_pedido: CreditRequestStatus = CreditRequestStatus.PENDENTE


class CreditInterviewData(BaseModel):
    """
    Structured data collected during the credit interview flow.

    Field names are canonical and must not be renamed.
    Validators are deterministic — no LLM, no external calls.
    """

    renda_mensal: float = Field(ge=0, le=1_000_000)
    tipo_emprego: EmploymentType
    despesas_fixas_mensais: float = Field(ge=0, le=1_000_000)
    numero_dependentes: int = Field(ge=0)
    tem_dividas_ativas: bool
