"""
AuthService — authenticates customers by matching CPF + data_nascimento against the repository.
Source of truth: REQUIREMENTS.md FR-AUTH-001 through FR-AUTH-006, TEST_PLAN.md section 6.3.
"""

from dataclasses import dataclass

from app.schemas.customer import Customer


@dataclass
class AuthResult:
    """
    Typed result returned by AuthService.authenticate.

    Contains only structured data — no UI messages.
    Authentication failure reasons are enumerated, not narrative.
    """

    success: bool
    customer: Customer | None = None
    failure_reason: str | None = None  # "unknown_cpf" | "wrong_birth_date"


class AuthService:
    """
    Authenticates customers by CPF and date of birth.

    Rules (REQUIREMENTS.md):
    - CPF must be preserved as string (including leading zeros).
    - Service does NOT own auth_attempts counting — that belongs to the graph node.
    - Service does NOT produce UI messages — only typed AuthResult.
    - Service does NOT access CSV directly — it uses a repository.
    - Service does NOT block sessions — StateGuard + triage_node handle that.

    Dependency: accepts a repository that implements find_by_cpf.
    """

    @staticmethod
    def authenticate(cpf: str, data_nascimento: str, repository) -> AuthResult:
        """
        Attempt to authenticate a customer.

        Args:
            cpf: Customer CPF as string (must preserve leading zeros).
            data_nascimento: Birth date in ISO 8601 format (YYYY-MM-DD).
            repository: Object with find_by_cpf(cpf: str) -> Customer | None.

        Returns:
            AuthResult with success=True and customer if matched,
            or success=False with failure_reason otherwise.
        """
        customer = repository.find_by_cpf(cpf)
        if customer is None:
            return AuthResult(success=False, customer=None, failure_reason="unknown_cpf")
        if customer.data_nascimento != data_nascimento:
            return AuthResult(success=False, customer=None, failure_reason="wrong_birth_date")
        return AuthResult(success=True, customer=customer, failure_reason=None)
