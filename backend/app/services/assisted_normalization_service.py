"""Deterministic-first normalization with constrained LLM fallback."""

from __future__ import annotations

import re
import unicodedata

from app.schemas.credit import EmploymentType
from app.services.normalizer_service import NormalizationError, NormalizerService


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


class AssistedNormalizationService:
    """Normalize user inputs safely, using LLM only as a constrained fallback."""

    # Deterministic affirmative phrases (case-/accent-insensitive after strip)
    _AFFIRMATIVE_PHRASES: frozenset[str] = frozenset({
        "ok", "pode ser", "pode", "claro", "claro que sim", "com certeza",
        "bora", "vamos lá", "vamos la", "por favor", "quero sim", "quero",
        "sim pode ser", "tá bom", "ta bom", "tá", "ta", "combinado",
        "aceito", "aceitar", "topo", "vai", "beleza", "ótimo", "otimo",
        "perfeito", "certo", "isso", "exato", "afirmativo", "com prazer",
        "positivo", "claro que pode", "vá em frente", "va em frente",
    })

    # Deterministic denial phrases
    _DENIAL_PHRASES: frozenset[str] = frozenset({
        "não quero", "nao quero", "prefiro não", "prefiro nao",
        "deixa pra lá", "deixa pra la", "agora não", "agora nao",
        "em outra hora", "talvez depois", "não preciso", "nao preciso",
        "não obrigado", "nao obrigado", "não, obrigado", "nao, obrigado",
        "dispenso", "não tenho interesse", "nao tenho interesse",
        "não quero agora", "nao quero agora", "negativo",
    })

    @staticmethod
    def normalize_confirmation(
        text: str,
        interpreter: object | None = None,
        *,
        extra_guidance: str = "",
        extra_examples: dict[str, str] | None = None,
    ) -> bool:
        try:
            return NormalizerService.normalize_boolean(text)
        except NormalizationError:
            stripped = _strip_accents((text or "").strip().lower())
            if stripped in AssistedNormalizationService._AFFIRMATIVE_PHRASES:
                return True
            if stripped in AssistedNormalizationService._DENIAL_PHRASES:
                return False

            guidance = (
                "Decide whether the user is accepting or declining a banking follow-up. "
                "Map short confirmations, enthusiastic phrases, or indirect agreements to accepted. "
                "Map refusals, hesitations that lean negative, or deferral phrases to declined. "
            )
            if extra_guidance:
                guidance += extra_guidance

            examples: dict[str, str] = {
                "ok": "accepted",
                "pode ser": "accepted",
                "claro": "accepted",
                "bora": "accepted",
                "vamos lá": "accepted",
                "quero sim": "accepted",
                "melhor nao": "declined",
                "não quero": "declined",
                "prefiro não": "declined",
                "deixa pra lá": "declined",
            }
            if extra_examples:
                examples.update(extra_examples)

            interpreted = AssistedNormalizationService._interpret_choice(
                interpreter=interpreter,
                user_message=text,
                field_name="confirmation",
                allowed_values=["accepted", "declined", "unknown"],
                guidance=guidance,
                examples=examples,
            )
            if interpreted == "accepted":
                return True
            if interpreted == "declined":
                return False
            raise NormalizationError("Could not normalize confirmation answer")

    @staticmethod
    def normalize_employment(text: str, interpreter: object | None = None) -> EmploymentType:
        try:
            return NormalizerService.normalize_employment(text)
        except NormalizationError:
            # Deterministic extended mappings before LLM fallback
            stripped = _strip_accents((text or "").strip().lower())
            _FORMAL_ALIASES = {
                "clt", "registrado", "fichado", "emprego formal", "setor publico",
                "servidor publico", "funcionario publico", "concursado",
                "aposentado", "pensionista",
            }
            _AUTONOMO_ALIASES = {
                "pj", "pessoa juridica", "mei", "microempreendedor",
                "faco bicos", "bicos", "freelancer", "freela",
                "autonomo", "por conta propria", "trabalho por conta",
            }
            _DESEMPREGADO_ALIASES = {
                "desempregado", "sem emprego", "sem trabalho", "desocupado",
                "procurando emprego", "fui demitido", "estou desempregado",
            }
            if stripped in _FORMAL_ALIASES:
                return EmploymentType.FORMAL
            if stripped in _AUTONOMO_ALIASES:
                return EmploymentType.AUTONOMO
            if stripped in _DESEMPREGADO_ALIASES:
                return EmploymentType.DESEMPREGADO

            interpreted = AssistedNormalizationService._interpret_choice(
                interpreter=interpreter,
                user_message=text,
                field_name="employment_type",
                allowed_values=["formal", "autonomo", "desempregado", "unknown"],
                guidance=(
                    "Classify the user's employment status into banking workflow categories. "
                    "'formal' = CLT, public servant, retired/pensioner; "
                    "'autonomo' = PJ, MEI, freelancer, gig work, self-employed; "
                    "'desempregado' = unemployed or job-seeking."
                ),
                examples={
                    "trabalho registrado": "formal",
                    "servidor publico": "formal",
                    "aposentado": "formal",
                    "faço bicos": "autonomo",
                    "MEI": "autonomo",
                    "PJ": "autonomo",
                    "estou sem trabalho": "desempregado",
                },
            )
            mapping = {
                "formal": EmploymentType.FORMAL,
                "autonomo": EmploymentType.AUTONOMO,
                "desempregado": EmploymentType.DESEMPREGADO,
            }
            if interpreted in mapping:
                return mapping[interpreted]
            raise NormalizationError("Could not normalize employment type")

    @staticmethod
    def normalize_dependents(text: str, interpreter: object | None = None) -> int:
        stripped = _strip_accents((text or "").strip().lower())
        if stripped.isdigit():
            return int(stripped)

        zero_aliases = {
            "nenhum",
            "nenhuma",
            "sem dependentes",
            "nao tenho dependentes",
            "não tenho dependentes",
        }
        if stripped in zero_aliases:
            return 0

        match = re.fullmatch(r"(\d+) dependentes?", stripped)
        if match:
            return int(match.group(1))

        interpreted = AssistedNormalizationService._interpret_choice(
            interpreter=interpreter,
            user_message=text,
            field_name="dependents_count",
            allowed_values=[*(str(value) for value in range(0, 11)), "unknown"],
            guidance=(
                "Infer the number of financial dependents from the user's answer. "
                "Return a single integer string between 0 and 10, or unknown."
            ),
            examples={
                "nenhum": "0",
                "dois filhos": "2",
                "tenho 3": "3",
            },
        )
        if interpreted is not None and interpreted.isdigit():
            return int(interpreted)
        raise NormalizationError("Could not normalize dependents count")

    @staticmethod
    def normalize_debts_answer(text: str, interpreter: object | None = None) -> bool:
        try:
            return NormalizerService.normalize_boolean(text)
        except NormalizationError:
            stripped = _strip_accents((text or "").strip().lower())
            _DEBT_TRUE = {
                "tenho dividas", "possuo dividas", "tenho uns cartoes",
                "tenho cartoes", "algumas contas abertas", "tenho financiamento",
                "tenho emprestimo", "estou devendo", "tenho pendencias",
            }
            _DEBT_FALSE = {
                "estou limpo", "sem dividas", "nome limpo", "nao tenho dividas",
                "nao devo nada", "estou quite", "quite",
            }
            if stripped in _DEBT_TRUE:
                return True
            if stripped in _DEBT_FALSE:
                return False

            interpreted = AssistedNormalizationService._interpret_choice(
                interpreter=interpreter,
                user_message=text,
                field_name="active_debts",
                allowed_values=["true", "false", "unknown"],
                guidance=(
                    "Determine whether the user says they currently have active debts or financial obligations. "
                    "'true' = has debts, cards, loans, financing; 'false' = no debts, clean credit record."
                ),
                examples={
                    "tenho algumas contas abertas": "true",
                    "tenho uns cartões": "true",
                    "estou limpo": "false",
                    "sem dividas": "false",
                    "estou sem dívidas": "false",
                },
            )
            if interpreted == "true":
                return True
            if interpreted == "false":
                return False
            raise NormalizationError("Could not normalize debts answer")

    @staticmethod
    def _interpret_choice(
        *,
        interpreter: object | None,
        user_message: str,
        field_name: str,
        allowed_values: list[str],
        guidance: str,
        examples: dict[str, str],
    ) -> str | None:
        if interpreter is None or not hasattr(interpreter, "interpret_choice"):
            return None
        return interpreter.interpret_choice(
            user_message=user_message,
            field_name=field_name,
            allowed_values=allowed_values,
            guidance=guidance,
            examples=examples,
        )