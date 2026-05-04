import pytest

from app.schemas.credit import EmploymentType
from app.services.assisted_normalization_service import AssistedNormalizationService
from app.services.normalizer_service import NormalizationError
from tests.conftest import FakeResponseInterpreter


def test_normalize_confirmation_accepts_pode_ser_deterministically() -> None:
    # "pode ser" is now in the deterministic affirmative set — no LLM needed
    result = AssistedNormalizationService.normalize_confirmation("pode ser", interpreter=None)
    assert result is True


def test_normalize_confirmation_accepts_extended_phrases_without_llm() -> None:
    for phrase in ("claro", "bora", "vamos lá", "aceito", "beleza", "perfeito"):
        assert AssistedNormalizationService.normalize_confirmation(phrase, interpreter=None) is True


def test_normalize_confirmation_rejects_denial_phrases_without_llm() -> None:
    for phrase in ("não quero", "prefiro não", "deixa pra lá", "agora não"):
        assert AssistedNormalizationService.normalize_confirmation(phrase, interpreter=None) is False


def test_normalize_confirmation_uses_interpreter_for_truly_ambiguous_phrase() -> None:
    # A phrase not in either deterministic set should fall back to interpreter
    interpreter = FakeResponseInterpreter({("confirmation", "talvez sim"): "accepted"})

    result = AssistedNormalizationService.normalize_confirmation(
        "talvez sim",
        interpreter=interpreter,
    )

    assert result is True
    assert len(interpreter.calls) == 1


def test_normalize_dependents_accepts_nenhum_without_llm() -> None:
    assert AssistedNormalizationService.normalize_dependents("nenhum") == 0


def test_normalize_dependents_uses_interpreter_for_natural_phrase() -> None:
    interpreter = FakeResponseInterpreter({("dependents_count", "dois filhos"): "2"})

    result = AssistedNormalizationService.normalize_dependents(
        "dois filhos",
        interpreter=interpreter,
    )

    assert result == 2


def test_normalize_employment_uses_interpreter_when_deterministic_parser_fails() -> None:
    interpreter = FakeResponseInterpreter({("employment_type", "faço bicos"): "autonomo"})

    result = AssistedNormalizationService.normalize_employment(
        "faço bicos",
        interpreter=interpreter,
    )

    assert result == EmploymentType.AUTONOMO


def test_normalize_confirmation_raises_when_interpretation_is_still_unknown() -> None:
    with pytest.raises(NormalizationError):
        AssistedNormalizationService.normalize_confirmation("talvez", interpreter=None)