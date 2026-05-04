"""
RegistrationService — new customer onboarding logic.

Handles the creation of new customers during the registration flow initiated
by the triage agent when a user identifies themselves as not yet a customer.

Rules:
- Does not write CSV directly; delegates to CustomerRepository.
- Score and initial limit are deterministic (no LLM).
- Validates CPF format and name before delegating to repository.
- Raises DuplicateCpfError (re-exported) when CPF already exists.
"""

from __future__ import annotations

from app.repositories.customer_repository import CustomerRepository, DuplicateCpfError
from app.repositories.score_limit_repository import ScoreLimitRepository
from app.schemas.customer import Customer

# Re-export for convenient import in nodes.py
__all__ = ["RegistrationService", "DuplicateCpfError"]

# New customers start with an entry-level score that qualifies for a R$2.500 limit
# and naturally incentivises them to try the financial interview to improve it.
_INITIAL_SCORE = 300


class RegistrationService:
    """Stateless service for new customer registration."""

    @staticmethod
    def register_new_customer(
        name: str,
        cpf: str,
        birth_date: str,
        customer_repository: CustomerRepository,
        score_limit_repository: ScoreLimitRepository,
    ) -> Customer:
        """
        Create and persist a new customer.

        Args:
            name: Full name as provided by the user (stripped).
            cpf: Validated 11-digit CPF string.
            birth_date: Normalised ISO date string (YYYY-MM-DD).
            customer_repository: Repository for customer CSV persistence.
            score_limit_repository: Used to resolve the initial credit limit.

        Returns:
            The newly created Customer object.

        Raises:
            ValueError: if name is blank or cpf is not 11 digits.
            DuplicateCpfError: if the CPF is already registered.
        """
        name = name.strip()
        if not name:
            raise ValueError("name must not be blank")
        if not cpf.isdigit() or len(cpf) != 11:
            raise ValueError(f"cpf must be 11 digits, got {cpf!r}")

        # Resolve initial limit from the score-limit table — consistent with
        # CreditService so the same business rules apply for new customers.
        initial_limit = score_limit_repository.find_max_limit_for_score(_INITIAL_SCORE)

        customer = Customer(
            cpf=cpf,
            data_nascimento=birth_date,
            nome=name,
            score_atual=_INITIAL_SCORE,
            limite_credito=initial_limit,
        )

        # create_customer raises DuplicateCpfError if CPF exists (inside lock).
        customer_repository.create_customer(customer)
        return customer
