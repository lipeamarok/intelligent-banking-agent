"""
ScoreLimitRepository — CSV repository implementation — Phase 5.

Reads the score–limit table from score_limite.csv.
Source of truth: REQUIREMENTS.md FR-CREDIT-005, TEST_PLAN.md section 5.2.

CSV format expected:
    score_minimo,score_maximo,limite_maximo_permitido
    0,299,1000.00
    300,499,2500.00
    500,699,5000.00
    700,849,10000.00
    850,1000,20000.00
"""

import csv
from pathlib import Path

_EXPECTED_HEADER = ["score_minimo", "score_maximo", "limite_maximo_permitido"]


class ScoreLimitRepository:
    """
    Repository for reading the credit score → maximum allowed limit table.

    This CSV is read-only at runtime.
    """

    def __init__(self, csv_path: Path) -> None:
        self._path = csv_path

    def find_max_limit_for_score(self, score: int) -> float:
        """
        Return the maximum allowed credit limit for the given score.

        Args:
            score: Customer's current score, must be in [0, 1000].

        Returns:
            Maximum allowed credit limit as float.

        Raises:
            FileNotFoundError: if the CSV file does not exist.
            ValueError: if no matching range is found for the given score.
        """
        if not self._path.exists():
            raise FileNotFoundError(f"CSV file not found: {self._path}")
        if not (0 <= score <= 1000):
            raise ValueError(
                f"score must be in [0, 1000], got {score}. "
                "Matches Customer.score_atual schema constraint."
            )

        with open(self._path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if list(reader.fieldnames or []) != _EXPECTED_HEADER:
                raise ValueError(
                    f"Unexpected CSV header: {reader.fieldnames}. "
                    f"Expected: {_EXPECTED_HEADER}"
                )
            for row in reader:
                try:
                    low = int(row["score_minimo"])
                    high = int(row["score_maximo"])
                    limit = float(row["limite_maximo_permitido"])
                except (KeyError, ValueError) as exc:
                    raise ValueError(f"Corrupted score_limite row: {row!r}") from exc

                if low <= score <= high:
                    return limit

        raise ValueError(
            f"No score range found for score={score}. "
            "Check score_limite.csv for complete coverage."
        )
