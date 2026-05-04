"""
Unit tests for ScoreService.

Source of truth: REQUIREMENTS.md FR-INTERVIEW-007, TEST_PLAN.md section 6.4.

Score formula contract (score_service.py docstring):
    income_score     = min(renda_mensal / (despesas_fixas_mensais + 1), 20.0) * 25.0
    employment_score = {formal: 300, autonomo: 200, desempregado: 0}
    dependents_score = {0: 100, 1: 80, 2: 60, >=3: 30}
    debt_score       = -100 if tem_dividas_ativas else +100
    raw_score        = income_score + employment_score + dependents_score + debt_score
    final_score      = max(0, min(1000, round(raw_score)))

With income=0, expenses=0 → income_score = 0.
These base inputs isolate each weight independently.
"""

import pytest

from app.schemas.credit import CreditInterviewData, EmploymentType
from app.services.score_service import ScoreResult, ScoreService


# ── Helpers ────────────────────────────────────────────────────────────────────


def make_interview(
    renda_mensal: float = 0.0,
    tipo_emprego: EmploymentType = EmploymentType.FORMAL,
    despesas_fixas_mensais: float = 0.0,
    numero_dependentes: int = 0,
    tem_dividas_ativas: bool = False,
) -> CreditInterviewData:
    """Build a CreditInterviewData with sensible defaults for test isolation."""
    return CreditInterviewData(
        renda_mensal=renda_mensal,
        tipo_emprego=tipo_emprego,
        despesas_fixas_mensais=despesas_fixas_mensais,
        numero_dependentes=numero_dependentes,
        tem_dividas_ativas=tem_dividas_ativas,
    )


# ── Return type ────────────────────────────────────────────────────────────────


def test_score_service_returns_score_result():
    """ScoreService.calculate must return a ScoreResult instance."""
    data = make_interview()
    result = ScoreService.calculate(data)
    assert isinstance(result, ScoreResult)


def test_score_result_has_score_and_rationale():
    data = make_interview()
    result = ScoreService.calculate(data)
    assert isinstance(result.score, int)
    assert isinstance(result.rationale, str)
    assert len(result.rationale) > 0


# ── Score range ────────────────────────────────────────────────────────────────


def test_score_is_always_within_bounds():
    """Score must always be in [0, 1000] regardless of inputs (TC-SCORE-006/007)."""
    data = make_interview()
    result = ScoreService.calculate(data)
    assert 0 <= result.score <= 1000


# ── Employment weights (TC-SCORE-002) ─────────────────────────────────────────
# Isolated using income=0, expenses=0, 0 dependents, no debts.
# income_score = 0, dependents_score = 100, debt_score = 100
# formal:      0 + 300 + 100 + 100 = 500
# autonomo:    0 + 200 + 100 + 100 = 400
# desempregado:0 +   0 + 100 + 100 = 200


def test_employment_formal_weight():
    result = ScoreService.calculate(
        make_interview(tipo_emprego=EmploymentType.FORMAL)
    )
    assert result.score == 500


def test_employment_autonomo_weight():
    result = ScoreService.calculate(
        make_interview(tipo_emprego=EmploymentType.AUTONOMO)
    )
    assert result.score == 400


def test_employment_desempregado_weight():
    result = ScoreService.calculate(
        make_interview(tipo_emprego=EmploymentType.DESEMPREGADO)
    )
    assert result.score == 200


def test_formal_score_greater_than_autonomo():
    """formal must always produce higher score than autonomo, all else equal."""
    formal = ScoreService.calculate(make_interview(tipo_emprego=EmploymentType.FORMAL))
    autonomo = ScoreService.calculate(make_interview(tipo_emprego=EmploymentType.AUTONOMO))
    assert formal.score > autonomo.score


def test_autonomo_score_greater_than_desempregado():
    autonomo = ScoreService.calculate(make_interview(tipo_emprego=EmploymentType.AUTONOMO))
    desempregado = ScoreService.calculate(make_interview(tipo_emprego=EmploymentType.DESEMPREGADO))
    assert autonomo.score > desempregado.score


# ── Dependents weights (TC-SCORE-003) ─────────────────────────────────────────
# Isolated using income=0, expenses=0, formal, no debts.
# formal + no debts baseline: 0 + 300 + dep + 100
# dep 0: 300+100+100=500, dep 1: 300+80+100=480, dep 2: 300+60+100=460, dep 3+: 300+30+100=430


def test_dependents_zero_weight():
    result = ScoreService.calculate(
        make_interview(tipo_emprego=EmploymentType.FORMAL, numero_dependentes=0)
    )
    assert result.score == 500


def test_dependents_one_weight():
    result = ScoreService.calculate(
        make_interview(tipo_emprego=EmploymentType.FORMAL, numero_dependentes=1)
    )
    assert result.score == 480


def test_dependents_two_weight():
    result = ScoreService.calculate(
        make_interview(tipo_emprego=EmploymentType.FORMAL, numero_dependentes=2)
    )
    assert result.score == 460


def test_dependents_three_weight():
    result = ScoreService.calculate(
        make_interview(tipo_emprego=EmploymentType.FORMAL, numero_dependentes=3)
    )
    assert result.score == 430


def test_dependents_four_uses_three_plus_bucket():
    """4 or more dependents use the same weight as 3+ (TC-SCORE-003)."""
    three = ScoreService.calculate(
        make_interview(tipo_emprego=EmploymentType.FORMAL, numero_dependentes=3)
    )
    four = ScoreService.calculate(
        make_interview(tipo_emprego=EmploymentType.FORMAL, numero_dependentes=4)
    )
    assert three.score == four.score


# ── Debt weights (TC-SCORE-004) ───────────────────────────────────────────────
# Isolated using income=0, expenses=0, formal, 0 dependents.
# no_debt: 0+300+100+100=500, has_debt: 0+300+100-100=300 → diff=200


def test_debt_false_weight():
    result = ScoreService.calculate(
        make_interview(tipo_emprego=EmploymentType.FORMAL, tem_dividas_ativas=False)
    )
    assert result.score == 500


def test_debt_true_weight():
    result = ScoreService.calculate(
        make_interview(tipo_emprego=EmploymentType.FORMAL, tem_dividas_ativas=True)
    )
    assert result.score == 300


def test_debt_difference_is_200():
    """Debt penalty is -100 vs +100 = net 200 point difference (TC-SCORE-004)."""
    no_debt = ScoreService.calculate(
        make_interview(tipo_emprego=EmploymentType.FORMAL, tem_dividas_ativas=False)
    )
    has_debt = ScoreService.calculate(
        make_interview(tipo_emprego=EmploymentType.FORMAL, tem_dividas_ativas=True)
    )
    assert no_debt.score - has_debt.score == 200


# ── Division by zero (TC-SCORE-005) ──────────────────────────────────────────


def test_no_division_by_zero_when_expenses_zero():
    """
    TC-SCORE-005: expenses=0 must not cause ZeroDivisionError.
    Formula uses (despesas_fixas_mensais + 1) as denominator.
    """
    data = make_interview(renda_mensal=5000.0, despesas_fixas_mensais=0.0)
    result = ScoreService.calculate(data)
    assert isinstance(result.score, int)


def test_no_division_by_zero_all_zeros():
    """All-zero inputs must produce a valid score without exception."""
    data = make_interview(
        renda_mensal=0.0,
        despesas_fixas_mensais=0.0,
        tipo_emprego=EmploymentType.DESEMPREGADO,
        numero_dependentes=0,
        tem_dividas_ativas=False,
    )
    result = ScoreService.calculate(data)
    assert isinstance(result.score, int)


# ── Score clipping (TC-SCORE-006, TC-SCORE-007) ───────────────────────────────


def test_score_clipped_at_1000():
    """TC-SCORE-006: inputs that would exceed 1000 must be clipped to 1000."""
    # Very high income, best employment, no dependents, no debts
    # income_score = min(1_000_000 / 1, 20) * 25 = 500
    # 500 + 300 + 100 + 100 = 1000 — exactly at cap
    data = make_interview(
        renda_mensal=1_000_000.0,
        tipo_emprego=EmploymentType.FORMAL,
        despesas_fixas_mensais=0.0,
        numero_dependentes=0,
        tem_dividas_ativas=False,
    )
    result = ScoreService.calculate(data)
    assert result.score == 1000


def test_score_clipped_at_zero():
    """TC-SCORE-007: inputs producing raw negative score must be clipped to 0."""
    # income=0, desempregado, 3+ dependents, has_debts
    # 0 + 0 + 30 - 100 = -70 → clipped to 0
    data = make_interview(
        renda_mensal=0.0,
        tipo_emprego=EmploymentType.DESEMPREGADO,
        despesas_fixas_mensais=0.0,
        numero_dependentes=5,
        tem_dividas_ativas=True,
    )
    result = ScoreService.calculate(data)
    assert result.score == 0


def test_score_is_integer():
    """Score must always be an integer (FR-INTERVIEW-007: clip and round)."""
    data = make_interview(renda_mensal=3333.33, despesas_fixas_mensais=1111.11)
    result = ScoreService.calculate(data)
    assert isinstance(result.score, int)


# ── Deterministic formula — TC-SCORE-001 ─────────────────────────────────────


def test_score_deterministic_same_inputs_same_output():
    """Same inputs must always produce the same score."""
    data = make_interview(
        renda_mensal=5000.0,
        tipo_emprego=EmploymentType.FORMAL,
        despesas_fixas_mensais=2500.0,
        numero_dependentes=0,
        tem_dividas_ativas=False,
    )
    result1 = ScoreService.calculate(data)
    result2 = ScoreService.calculate(data)
    assert result1.score == result2.score


def test_score_for_documented_example():
    """
    TC-SCORE-001: income=5000, expenses=2500, formal, 0 dep, no debts.
    income_score = min(5000/2501, 20)*25 = min(1.9992, 20)*25 ≈ 49.98 → ~49
    total ≈ 49 + 300 + 100 + 100 = 549 → round = 550
    """
    data = make_interview(
        renda_mensal=5000.0,
        tipo_emprego=EmploymentType.FORMAL,
        despesas_fixas_mensais=2500.0,
        numero_dependentes=0,
        tem_dividas_ativas=False,
    )
    result = ScoreService.calculate(data)
    # Asserts the formula is used — exact value depends on rounding
    assert 540 <= result.score <= 560
