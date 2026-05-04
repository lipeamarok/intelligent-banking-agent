"""
CreditService — handles credit limit consultation and credit increase request evaluation.
Source of truth: REQUIREMENTS.md FR-CREDIT-001 through FR-CREDIT-006,
                  TEST_PLAN.md section 6.5.
"""

from dataclasses import dataclass

from app.schemas.credit import CreditLimitRequest, CreditRequestStatus
from app.schemas.customer import Customer


@dataclass
class CreditResult:
    """Typed result returned by CreditService.evaluate_limit_request."""

    approved: bool
    request: CreditLimitRequest   # Final request with status set
    rationale: str                # Score, requested limit, allowed limit summary
    max_allowed: float            # Maximum limit allowed for current score


class CreditService:
    """
    Evaluates credit limit requests against the score–limit table.

    Rules (REQUIREMENTS.md):
    - Service does NOT calculate score.
    - Service does NOT authenticate the customer.
    - Service does NOT write CSV directly — uses repository layer.
    - Service does NOT produce UI messages — returns CreditResult.
    - Approval/rejection is based only on score table lookup.
    - Every evaluated request must be persisted via credit_request_repo.
    """

    @staticmethod
    def get_current_limit(customer: Customer) -> float:
        """
        Return the current credit limit for the authenticated customer.

        Args:
            customer: Authenticated Customer object loaded from repository.

        Returns:
            Current limite_credito as float.
        """
        return float(customer.limite_credito)

    @staticmethod
    def evaluate_limit_request(
        request: CreditLimitRequest,
        customer: Customer,
        score_limit_repo,
        credit_request_repo,
    ) -> CreditResult:
        """
        Evaluate a credit limit increase request.

        Args:
            request: Validated CreditLimitRequest with status=PENDENTE.
            customer: Authenticated Customer with current score.
            score_limit_repo: Object with find_max_limit_for_score(score) -> float.
            credit_request_repo: Object with append(request) -> None.

        Returns:
            CreditResult with approved status and persisted request.

        Raises:
            ValueError: if request.novo_limite_solicitado <= 0 or > 1_000_000.
        """
        max_allowed = score_limit_repo.find_max_limit_for_score(customer.score_atual)
        approved = request.novo_limite_solicitado <= max_allowed

        status = CreditRequestStatus.APROVADO if approved else CreditRequestStatus.REJEITADO
        final_request = request.model_copy(update={"status_pedido": status})

        credit_request_repo.append(final_request)

        rationale = (
            f"score={customer.score_atual} max_allowed={max_allowed} "
            f"requested={request.novo_limite_solicitado} "
            f"decision={'approved' if approved else 'rejected'}"
        )

        return CreditResult(approved=approved, request=final_request, rationale=rationale, max_allowed=max_allowed)
