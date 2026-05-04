"""
ScoreService — calculates a deterministic credit score from CreditInterviewData.
Source of truth: REQUIREMENTS.md FR-INTERVIEW-007, TEST_PLAN.md section 6.4.

Score formula (documented contract — implementation must follow exactly):

    income_score      = min(renda_mensal / (despesas_fixas_mensais + 1), 20.0) * 25.0
    employment_score  = {formal: 300, autonomo: 200, desempregado: 0}
    dependents_score  = {0: 100, 1: 80, 2: 60, >=3: 30}
    debt_score        = -100 if tem_dividas_ativas else +100

    raw_score = income_score + employment_score + dependents_score + debt_score
    score     = max(0, min(1000, round(raw_score)))

Maximum possible: min(∞→20)*25 + 300 + 100 + 100 = 1000
Minimum possible: 0 + 0 + 30 - 100 = -70 → clipped to 0
Division-by-zero is prevented by (despesas_fixas_mensais + 1).
"""

from dataclasses import dataclass

from app.schemas.credit import CreditInterviewData


@dataclass
class ScoreResult:
    """Typed result returned by ScoreService.calculate."""

    score: int          # Final clamped score, 0–1000
    rationale: str      # Short technical explanation of the score components


class ScoreService:
    """
    Calculates a deterministic credit score.

    Rules (REQUIREMENTS.md):
    - Formula is deterministic — no LLM, no randomness.
    - Score is always an integer in [0, 1000].
    - Division by zero is prevented using (expenses + 1).
    - Service does NOT persist the score — that is done by the repository layer.
    - Service does NOT authenticate the customer.
    - Service does NOT make approval/rejection decisions.
    """

    @staticmethod
    def calculate(data: CreditInterviewData) -> ScoreResult:
        """
        Calculate a credit score from validated interview data.

        Args:
            data: Validated CreditInterviewData. All fields must already be
                  normalized; do not pass raw user text.

        Returns:
            ScoreResult with final score [0, 1000] and technical rationale.

        Raises:
            ValueError: if data contains negative values (should not occur if
                        CreditInterviewData validation was applied).
        """
        from app.schemas.credit import EmploymentType

        income_score = min(
            data.renda_mensal / (data.despesas_fixas_mensais + 1), 20.0
        ) * 25.0

        _employment_map = {
            EmploymentType.FORMAL: 300,
            EmploymentType.AUTONOMO: 200,
            EmploymentType.DESEMPREGADO: 0,
        }
        employment_score = _employment_map[data.tipo_emprego]

        if data.numero_dependentes == 0:
            dependents_score = 100
        elif data.numero_dependentes == 1:
            dependents_score = 80
        elif data.numero_dependentes == 2:
            dependents_score = 60
        else:
            dependents_score = 30

        debt_score = -100 if data.tem_dividas_ativas else 100

        raw_score = income_score + employment_score + dependents_score + debt_score
        final_score = max(0, min(1000, round(raw_score)))

        rationale = (
            f"income={income_score:.2f} employment={employment_score} "
            f"dependents={dependents_score} debt={debt_score} "
            f"raw={raw_score:.2f} final={final_score}"
        )

        return ScoreResult(score=final_score, rationale=rationale)
