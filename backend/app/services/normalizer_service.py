"""
NormalizerService — Phase 4 implementation.

Normalizes raw user text inputs to typed Python values.
Source of truth: REQUIREMENTS.md FR-INTERVIEW-002/003/004/005/006,
                  TEST_PLAN.md section 6.2 (TC-NORM-001 through TC-NORM-008).
"""

import re
import unicodedata
from datetime import date

from app.schemas.credit import EmploymentType


class NormalizationError(ValueError):
    """
    Raised when user input cannot be normalized to the required type.

    Callers must catch this and request clarification from the user.
    Must never be forwarded as-is to the frontend.
    """


def _strip_accents(s: str) -> str:
    """Remove diacritical marks from a unicode string."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _parse_br_number(s: str) -> float:
    """
    Parse a numeric string that may use Brazilian (. = thousands, , = decimal)
    or plain formatting. Returns float. Raises ValueError on parse failure.
    """
    s = s.strip()
    if "," in s and "." in s:
        last_dot = s.rindex(".")
        last_comma = s.rindex(",")
        if last_comma > last_dot:
            # Brazilian format: 5.000,00
            s = s.replace(".", "").replace(",", ".")
        else:
            # English format: 5,000.00
            s = s.replace(",", "")
    elif "," in s:
        # Only comma → decimal separator
        s = s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        # "5.000" → dot followed by exactly 3 digits → thousands separator
        if (
            len(parts) == 2
            and len(parts[1]) == 3
            and parts[1].isdigit()
            and parts[0].isdigit()
        ):
            s = s.replace(".", "")
        # else treat dot as decimal (e.g. "5.5")
    return float(s)


class NormalizerService:
    """
    Converts raw natural language user input to validated typed values.

    Rules:
    - All methods are deterministic — no LLM calls.
    - Ambiguous input raises NormalizationError.
    - Out-of-range input raises NormalizationError.
    - Never returns a value that would fail Pydantic schema validation.
    """

    @staticmethod
    def normalize_currency(text: str) -> float:
        """
        Normalize a monetary string to a float.

        Accepted formats (TC-NORM-001, TC-NORM-002):
            "R$ 5.000"       → 5000.0
            "R$ 5.000,00"    → 5000.0
            "5.000,00"       → 5000.0
            "5000 reais"     → 5000.0
            "10k"            → 10000.0

        Rejected inputs (TC-NORM-003, TC-NORM-004):
            "bastante", "alto", "baixo", "mais ou menos"  → NormalizationError
            Values above 1_000_000                        → NormalizationError

        Raises:
            NormalizationError: if the input is ambiguous, non-numeric, or out-of-range.
        """
        if not text or not text.strip():
            raise NormalizationError("Currency input is empty")

        t = _strip_accents(text.strip().lower())

        # Remove currency prefix "R$"
        t = re.sub(r"^r\$\s*", "", t).strip()

        # Remove common currency word suffixes
        t = re.sub(r"\s+(reais?|brl)$", "", t).strip()

        # Handle magnitude suffixes (generic, not phrase-specific)
        # Examples: 16k, 16 mil, 2 milhoes, 1,2 milhao, 16 contos
        magnitude_match = re.match(
            r"^([\d.,]+)\s*(k|mil|mi|m|milhao|milhoes|conto|contos)$",
            t,
        )
        if magnitude_match:
            magnitude = magnitude_match.group(2)
            multiplier = 1.0
            if magnitude in {"k", "mil", "conto", "contos"}:
                multiplier = 1000.0
            elif magnitude in {"mi", "m", "milhao", "milhoes"}:
                multiplier = 1_000_000.0

            try:
                value = _parse_br_number(magnitude_match.group(1)) * multiplier
            except ValueError:
                raise NormalizationError(
                    f"Cannot parse currency with magnitude from: {text!r}"
                )
        else:
            # Require at least one digit
            if not re.search(r"\d", t):
                raise NormalizationError(f"Cannot parse currency: {text!r}")
            try:
                value = _parse_br_number(t)
            except ValueError:
                raise NormalizationError(f"Cannot parse currency: {text!r}")

        if value < 0:
            raise NormalizationError(
                f"Negative value {value} is not allowed: {text!r}"
            )

        if value > 1_000_000:
            raise NormalizationError(
                f"Value {value} exceeds maximum allowed 1_000_000: {text!r}"
            )

        return value

    @staticmethod
    def normalize_boolean(text: str) -> bool:
        """
        Normalize a debt/yes-no answer to a boolean.

        Accepted as True (TC-NORM-005):
            "sim", "tenho dívidas", "yes", "possuo dívidas"

        Accepted as False (TC-NORM-005):
            "não", "nao", "sem dívidas", "no"

        Rejected (TC-NORM-006):
            "talvez", "não sei", "depende"  → NormalizationError

        Raises:
            NormalizationError: if the input is ambiguous.
        """
        normalized = _strip_accents(text.strip().lower())

        _TRUE = {
            "sim",
            "yes",
            "tenho dividas",
            "possuo dividas",
        }
        _FALSE = {
            "nao",
            "no",
            "sem dividas",
        }

        if normalized in _TRUE:
            return True
        if normalized in _FALSE:
            return False
        raise NormalizationError(f"Cannot determine boolean value from: {text!r}")

    @staticmethod
    def normalize_employment(text: str) -> EmploymentType:
        """
        Normalize an employment description to EmploymentType enum.

        Mappings (TC-NORM-007):
            "CLT"            → EmploymentType.FORMAL
            "autônomo"       → EmploymentType.AUTONOMO
            "autonomo"       → EmploymentType.AUTONOMO
            "sem emprego"    → EmploymentType.DESEMPREGADO

        Raises:
            NormalizationError: if the input does not map to a known employment type.
        """
        normalized = _strip_accents(text.strip().lower())

        _FORMAL = {"clt", "carteira assinada", "formal", "empregado", "empregada"}
        _AUTONOMO = {
            "autonomo",
            "freelancer",
            "liberal",
            "conta propria",
            "autonomo",
        }
        _DESEMPREGADO = {
            "desempregado",
            "desempregada",
            "sem emprego",
            "nao trabalho",
            "sem trabalho",
        }

        if normalized in _FORMAL:
            return EmploymentType.FORMAL
        if normalized in _AUTONOMO:
            return EmploymentType.AUTONOMO
        if normalized in _DESEMPREGADO:
            return EmploymentType.DESEMPREGADO
        raise NormalizationError(f"Cannot determine employment type from: {text!r}")

    @staticmethod
    def normalize_date(text: str) -> str:
        """
        Normalize a human date string to ISO 8601 YYYY-MM-DD format.

        Accepted format (TC-NORM-008):
            "12-05-1990"  → "1990-05-12"

        Raises:
            NormalizationError: if the date is invalid or unrecognizable.
        """
        t = text.strip()

        # DD-MM-YYYY
        if re.match(r"^\d{2}-\d{2}-\d{4}$", t):
            day_s, month_s, year_s = t.split("-")
            try:
                d = date(int(year_s), int(month_s), int(day_s))
                return d.isoformat()
            except ValueError:
                raise NormalizationError(f"Invalid date: {text!r}")

        raise NormalizationError(f"Unrecognized date format: {text!r}")
