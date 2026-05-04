"""
Unit tests for NormalizerService.

Source of truth: REQUIREMENTS.md FR-INTERVIEW-002–006,
                  TEST_PLAN.md section 6.2 (TC-NORM-001 through TC-NORM-008).
"""

import pytest

from app.schemas.credit import EmploymentType
from app.services.normalizer_service import NormalizationError, NormalizerService


# ── Currency normalization — valid inputs (TC-NORM-001, TC-NORM-002) ──────────


@pytest.mark.parametrize("text,expected", [
    ("R$ 5.000", 5000.0),
    ("R$ 5.000,00", 5000.0),
    ("5.000,00", 5000.0),
    ("5000 reais", 5000.0),
    ("5000", 5000.0),
    ("10k", 10000.0),
    ("1k", 1000.0),
    ("100K", 100000.0),
    ("16 mil", 16000.0),
    ("16 contos", 16000.0),
    ("0,9 milhao", 900000.0),
    ("0,9 milhão", 900000.0),
    ("R$ 0", 0.0),
    ("0", 0.0),
])
def test_normalize_currency_valid(text, expected):
    """TC-NORM-001/002: valid monetary strings produce expected float."""
    result = NormalizerService.normalize_currency(text)
    assert result == pytest.approx(expected)


# ── Currency normalization — ambiguous inputs (TC-NORM-003) ──────────────────


@pytest.mark.parametrize("text", [
    "bastante",
    "alto",
    "baixo",
    "mais ou menos",
    "muito",
    "pouco",
])
def test_normalize_currency_rejects_ambiguous(text):
    """TC-NORM-003: ambiguous text must raise NormalizationError."""
    with pytest.raises(NormalizationError):
        NormalizerService.normalize_currency(text)


def test_normalize_currency_rejects_empty_string():
    with pytest.raises(NormalizationError):
        NormalizerService.normalize_currency("")


def test_normalize_currency_rejects_whitespace_only():
    with pytest.raises(NormalizationError):
        NormalizerService.normalize_currency("   ")


# ── Currency normalization — out-of-range (TC-NORM-004) ──────────────────────


def test_normalize_currency_rejects_above_1_million():
    """TC-NORM-004: value > 1_000_000 must raise NormalizationError."""
    with pytest.raises(NormalizationError):
        NormalizerService.normalize_currency("1000001")


def test_normalize_currency_rejects_magnitude_value_above_1_million():
    with pytest.raises(NormalizationError):
        NormalizerService.normalize_currency("1,2 milhao")


def test_normalize_currency_rejects_two_millions_text():
    with pytest.raises(NormalizationError):
        NormalizerService.normalize_currency("2 milhoes")


def test_normalize_currency_rejects_1001k():
    with pytest.raises(NormalizationError):
        NormalizerService.normalize_currency("1001k")


def test_normalize_currency_accepts_exactly_1_million():
    """1_000_000 is the documented upper boundary — must be accepted."""
    result = NormalizerService.normalize_currency("1000000")
    assert result == pytest.approx(1_000_000.0)


def test_normalize_currency_accepts_1000k():
    result = NormalizerService.normalize_currency("1000k")
    assert result == pytest.approx(1_000_000.0)


# ── Boolean normalization — valid true inputs (TC-NORM-005) ──────────────────


@pytest.mark.parametrize("text", [
    "sim",
    "Sim",
    "SIM",
    "tenho dívidas",
    "tenho dividas",
    "yes",
    "possuo dívidas",
    "possuo dividas",
])
def test_normalize_boolean_true_inputs(text):
    """TC-NORM-005: debt-affirming inputs must return True."""
    result = NormalizerService.normalize_boolean(text)
    assert result is True


# ── Boolean normalization — valid false inputs (TC-NORM-005) ─────────────────


@pytest.mark.parametrize("text", [
    "não",
    "nao",
    "Não",
    "sem dívidas",
    "sem dividas",
    "no",
    "No",
])
def test_normalize_boolean_false_inputs(text):
    """TC-NORM-005: debt-denying inputs must return False."""
    result = NormalizerService.normalize_boolean(text)
    assert result is False


# ── Boolean normalization — ambiguous inputs (TC-NORM-006) ───────────────────


@pytest.mark.parametrize("text", [
    "talvez",
    "não sei",
    "nao sei",
    "depende",
    "talvez não",
    "acho que sim",
])
def test_normalize_boolean_rejects_ambiguous(text):
    """TC-NORM-006: ambiguous debt answers must raise NormalizationError."""
    with pytest.raises(NormalizationError):
        NormalizerService.normalize_boolean(text)


# ── Employment normalization (TC-NORM-007) ────────────────────────────────────


@pytest.mark.parametrize("text,expected", [
    ("CLT", EmploymentType.FORMAL),
    ("clt", EmploymentType.FORMAL),
    ("carteira assinada", EmploymentType.FORMAL),
    ("formal", EmploymentType.FORMAL),
    ("autônomo", EmploymentType.AUTONOMO),
    ("autonomo", EmploymentType.AUTONOMO),
    ("Autônomo", EmploymentType.AUTONOMO),
    ("freelancer", EmploymentType.AUTONOMO),
    ("sem emprego", EmploymentType.DESEMPREGADO),
    ("desempregado", EmploymentType.DESEMPREGADO),
    ("desempregada", EmploymentType.DESEMPREGADO),
    ("não trabalho", EmploymentType.DESEMPREGADO),
])
def test_normalize_employment_valid(text, expected):
    """TC-NORM-007: employment strings must map to correct EmploymentType."""
    result = NormalizerService.normalize_employment(text)
    assert result == expected


def test_normalize_employment_rejects_unknown():
    """Unrecognizable employment text must raise NormalizationError."""
    with pytest.raises(NormalizationError):
        NormalizerService.normalize_employment("estrela do rock")


# ── Date normalization (TC-NORM-008) ─────────────────────────────────────────


def test_normalize_date_dd_mm_yyyy_format():
    """TC-NORM-008: DD-MM-YYYY must be converted to YYYY-MM-DD."""
    result = NormalizerService.normalize_date("12-05-1990")
    assert result == "1990-05-12"


def test_normalize_date_rejects_slash_format():
    with pytest.raises(NormalizationError):
        NormalizerService.normalize_date("12/05/1990")


def test_normalize_date_rejects_iso_input_format():
    with pytest.raises(NormalizationError):
        NormalizerService.normalize_date("1990-05-12")


def test_normalize_date_rejects_invalid():
    """Invalid date strings must raise NormalizationError."""
    with pytest.raises(NormalizationError):
        NormalizerService.normalize_date("not-a-date")


def test_normalize_date_rejects_impossible_date():
    """Impossible date like 32/13/1990 must raise NormalizationError."""
    with pytest.raises(NormalizationError):
        NormalizerService.normalize_date("32/13/1990")


# ── Currency normalization — negative values (FR-CREDIT-003) ─────────────────


@pytest.mark.parametrize("text", [
    "-1",
    "-500",
    "R$ -500",
])
def test_normalize_currency_rejects_negative_values(text):
    """
    FR-CREDIT-003: negative values must be rejected with NormalizationError.
    NormalizerService must never return a value that fails CreditInterviewData
    schema validation (which uses Field(ge=0)).
    """
    with pytest.raises(NormalizationError):
        NormalizerService.normalize_currency(text)


def test_normalize_currency_zero_is_still_valid():
    """0 is the lower bound. It must remain accepted after the negative check."""
    assert NormalizerService.normalize_currency("0") == pytest.approx(0.0)


def test_normalize_currency_r_zero_is_still_valid():
    assert NormalizerService.normalize_currency("R$ 0") == pytest.approx(0.0)
