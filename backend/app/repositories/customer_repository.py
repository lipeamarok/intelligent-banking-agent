"""
CustomerRepository — CSV repository implementation — Phase 5.

Reads and writes customer data from/to clientes.csv.
Source of truth: REQUIREMENTS.md FR-AUTH-004, FR-INTERVIEW-008,
                  TEST_PLAN.md sections 5.1 and 6.6.

CSV format expected:
    cpf,data_nascimento,nome,score_atual,limite_credito
    12345678901,1990-05-12,Ana Silva,720,5000.00

Rules:
- CPF must always be read and written as string (preserve leading zeros).
- Atomic write strategy: write to .tmp first, validate, then replace original.
- Original file must never be corrupted by a failed write.
"""

import csv
import io
import os
from pathlib import Path

import portalocker

from app.schemas.customer import Customer

_EXPECTED_HEADER = ["cpf", "data_nascimento", "nome", "score_atual", "limite_credito"]
_LOCK_TIMEOUT = 5  # seconds


class DuplicateCpfError(Exception):
    """Raised when attempting to create a customer with a CPF that already exists."""


class CustomerRepository:
    """
    Repository for customer CSV persistence.

    All reads return typed Customer objects.
    All writes use atomic .tmp → replace strategy.
    """

    def __init__(self, csv_path: Path) -> None:
        self._path = csv_path

    def find_by_cpf(self, cpf: str) -> Customer | None:
        """
        Find a customer by CPF string.

        Args:
            cpf: Customer CPF as string. Leading zeros must be preserved.

        Returns:
            Customer if found, None otherwise.
        """
        if not self._path.exists():
            raise FileNotFoundError(f"CSV file not found: {self._path}")

        with open(self._path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if list(reader.fieldnames or []) != _EXPECTED_HEADER:
                raise ValueError(
                    f"Unexpected CSV header: {reader.fieldnames}. "
                    f"Expected: {_EXPECTED_HEADER}"
                )
            for row in reader:
                if row["cpf"] == cpf:
                    try:
                        return Customer(
                            cpf=str(row["cpf"]),
                            data_nascimento=row["data_nascimento"],
                            nome=row["nome"],
                            score_atual=int(row["score_atual"]),
                            limite_credito=float(row["limite_credito"]),
                        )
                    except Exception as exc:
                        raise ValueError(
                            f"Corrupted row for CPF {cpf!r}: {row!r}"
                        ) from exc
        return None

    def update_score(self, cpf: str, new_score: int) -> None:
        """
        Update the score_atual for the given CPF.

        Must use atomic write: .tmp file → validate → replace original.
        Must preserve the original CSV header exactly.
        Must preserve all other rows unchanged.

        Raises:
            FileNotFoundError: if the CSV file does not exist.
            ValueError: if new_score is outside [0, 1000].
        """
        if not self._path.exists():
            raise FileNotFoundError(f"CSV file not found: {self._path}")
        if not (0 <= new_score <= 1000):
            raise ValueError(f"new_score must be in [0, 1000], got {new_score}")

        tmp_path = self._path.with_suffix(".csv.tmp")
        lock_path = self._path.with_suffix(".csv.lock")
        try:
            with portalocker.Lock(str(lock_path), mode="w", timeout=_LOCK_TIMEOUT):
                with open(self._path, newline="", encoding="utf-8") as fh:
                    reader = csv.DictReader(fh)
                    if list(reader.fieldnames or []) != _EXPECTED_HEADER:
                        raise ValueError(
                            f"Unexpected CSV header: {reader.fieldnames}"
                        )
                    rows = list(reader)

                updated = False
                for row in rows:
                    if row["cpf"] == cpf:
                        row["score_atual"] = str(new_score)
                        updated = True

                if not updated:
                    raise KeyError(f"CPF not found: {cpf!r}")

                # Write to .tmp
                buf = io.StringIO()
                writer = csv.DictWriter(buf, fieldnames=_EXPECTED_HEADER, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
                tmp_path.write_text(buf.getvalue(), encoding="utf-8")

                # Validate .tmp — ADR-007 steps 5-7: header, columns, row shape
                with open(tmp_path, newline="", encoding="utf-8") as fh:
                    tmp_reader = csv.DictReader(fh)
                    if list(tmp_reader.fieldnames or []) != _EXPECTED_HEADER:
                        raise ValueError(
                            f".tmp header mismatch: {tmp_reader.fieldnames}"
                        )
                    check = list(tmp_reader)
                if len(check) != len(rows):
                    raise ValueError(
                        f".tmp row count {len(check)} != expected {len(rows)}"
                    )
                for chk_row in check:
                    Customer(
                        cpf=str(chk_row["cpf"]),
                        data_nascimento=chk_row["data_nascimento"],
                        nome=chk_row["nome"],
                        score_atual=int(chk_row["score_atual"]),
                        limite_credito=float(chk_row["limite_credito"]),
                    )

                os.replace(tmp_path, self._path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    def create_customer(self, customer: Customer) -> None:
        """
        Append a new customer row to the CSV.

        Uses the same atomic .tmp → validate → replace strategy as update_score
        and update_limit to prevent corruption on concurrent writes.

        Raises:
            FileNotFoundError: if the CSV file does not exist.
            DuplicateCpfError: if a customer with the same CPF already exists.
        """
        if not self._path.exists():
            raise FileNotFoundError(f"CSV file not found: {self._path}")

        tmp_path = self._path.with_suffix(".csv.tmp")
        lock_path = self._path.with_suffix(".csv.lock")
        try:
            with portalocker.Lock(str(lock_path), mode="w", timeout=_LOCK_TIMEOUT):
                with open(self._path, newline="", encoding="utf-8") as fh:
                    reader = csv.DictReader(fh)
                    if list(reader.fieldnames or []) != _EXPECTED_HEADER:
                        raise ValueError(
                            f"Unexpected CSV header: {reader.fieldnames}"
                        )
                    rows = list(reader)

                # Uniqueness check inside the lock (atomic read-then-write).
                for row in rows:
                    if row["cpf"] == customer.cpf:
                        raise DuplicateCpfError(
                            f"CPF {customer.cpf!r} already exists in {self._path.name}"
                        )

                new_row = {
                    "cpf": customer.cpf,
                    "data_nascimento": customer.data_nascimento,
                    "nome": customer.nome,
                    "score_atual": str(customer.score_atual),
                    "limite_credito": f"{float(customer.limite_credito):.2f}",
                }
                rows.append(new_row)

                buf = io.StringIO()
                writer = csv.DictWriter(
                    buf, fieldnames=_EXPECTED_HEADER, lineterminator="\n"
                )
                writer.writeheader()
                writer.writerows(rows)
                tmp_path.write_text(buf.getvalue(), encoding="utf-8")

                # Validate written file round-trips correctly.
                with open(tmp_path, newline="", encoding="utf-8") as fh:
                    tmp_reader = csv.DictReader(fh)
                    if list(tmp_reader.fieldnames or []) != _EXPECTED_HEADER:
                        raise ValueError(
                            f".tmp header mismatch: {tmp_reader.fieldnames}"
                        )
                    check = list(tmp_reader)
                if len(check) != len(rows):
                    raise ValueError(
                        f".tmp row count {len(check)} != expected {len(rows)}"
                    )
                for chk_row in check:
                    Customer(
                        cpf=str(chk_row["cpf"]),
                        data_nascimento=chk_row["data_nascimento"],
                        nome=chk_row["nome"],
                        score_atual=int(chk_row["score_atual"]),
                        limite_credito=float(chk_row["limite_credito"]),
                    )

                os.replace(tmp_path, self._path)
        except DuplicateCpfError:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    def update_limit(self, cpf: str, new_limit: float) -> None:
        """
        Update the limite_credito for the given CPF.

        Mirrors update_score: atomic .tmp → validate → replace original.
        Preserves CSV header and all other rows.

        Raises:
            FileNotFoundError: if the CSV file does not exist.
            ValueError: if new_limit is negative or above 1_000_000.
            KeyError: if the CPF is not present in the CSV.
        """
        if not self._path.exists():
            raise FileNotFoundError(f"CSV file not found: {self._path}")
        if new_limit < 0 or new_limit > 1_000_000:
            raise ValueError(
                f"new_limit must be in [0, 1_000_000], got {new_limit}"
            )

        tmp_path = self._path.with_suffix(".csv.tmp")
        lock_path = self._path.with_suffix(".csv.lock")
        try:
            with portalocker.Lock(str(lock_path), mode="w", timeout=_LOCK_TIMEOUT):
                with open(self._path, newline="", encoding="utf-8") as fh:
                    reader = csv.DictReader(fh)
                    if list(reader.fieldnames or []) != _EXPECTED_HEADER:
                        raise ValueError(
                            f"Unexpected CSV header: {reader.fieldnames}"
                        )
                    rows = list(reader)

                updated = False
                for row in rows:
                    if row["cpf"] == cpf:
                        row["limite_credito"] = f"{float(new_limit):.2f}"
                        updated = True

                if not updated:
                    raise KeyError(f"CPF not found: {cpf!r}")

                buf = io.StringIO()
                writer = csv.DictWriter(
                    buf, fieldnames=_EXPECTED_HEADER, lineterminator="\n"
                )
                writer.writeheader()
                writer.writerows(rows)
                tmp_path.write_text(buf.getvalue(), encoding="utf-8")

                with open(tmp_path, newline="", encoding="utf-8") as fh:
                    tmp_reader = csv.DictReader(fh)
                    if list(tmp_reader.fieldnames or []) != _EXPECTED_HEADER:
                        raise ValueError(
                            f".tmp header mismatch: {tmp_reader.fieldnames}"
                        )
                    check = list(tmp_reader)
                if len(check) != len(rows):
                    raise ValueError(
                        f".tmp row count {len(check)} != expected {len(rows)}"
                    )
                for chk_row in check:
                    Customer(
                        cpf=str(chk_row["cpf"]),
                        data_nascimento=chk_row["data_nascimento"],
                        nome=chk_row["nome"],
                        score_atual=int(chk_row["score_atual"]),
                        limite_credito=float(chk_row["limite_credito"]),
                    )

                os.replace(tmp_path, self._path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
