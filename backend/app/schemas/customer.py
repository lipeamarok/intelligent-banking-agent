"""
Customer domain model.

Source of truth: PROJECT.md (domain model names), REQUIREMENTS.md (validation rules).
No CSV access, no LLM, no authentication logic here.
"""

from datetime import date

from pydantic import BaseModel, Field, field_validator


class Customer(BaseModel):
    """Normalized customer record. Populated from CSV after successful authentication."""

    cpf: str
    data_nascimento: str
    nome: str
    score_atual: int = Field(ge=0, le=1000)
    limite_credito: float = Field(ge=0)

    @field_validator("data_nascimento")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        try:
            date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(
                "data_nascimento must be in ISO 8601 format: YYYY-MM-DD"
            ) from exc
        return v
