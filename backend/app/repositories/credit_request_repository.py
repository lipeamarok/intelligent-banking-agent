"""
CreditRequestRepository — CSV repository implementation — Phase 5.

Appends credit limit increase requests to solicitacoes_aumento_limite.csv.
Source of truth: REQUIREMENTS.md FR-CREDIT-004, TEST_PLAN.md section 5.3 and 6.6.

CSV format expected:
    cpf_cliente,data_hora_solicitacao,limite_atual,novo_limite_solicitado,status_pedido
"""

import csv
import io
import os
from datetime import datetime, timezone
from pathlib import Path

import portalocker

from app.schemas.credit import CreditLimitRequest

_EXPECTED_HEADER = [
    "cpf_cliente",
    "data_hora_solicitacao",
    "limite_atual",
    "novo_limite_solicitado",
    "status_pedido",
]
_LOCK_TIMEOUT = 5  # seconds


class CreditRequestRepository:
    """
    Repository for appending credit increase requests to CSV.

    Uses atomic write strategy: .tmp → validate → replace original.
    Must preserve the CSV header on every write.
    """

    def __init__(self, csv_path: Path) -> None:
        self._path = csv_path

    def append(self, request: CreditLimitRequest) -> None:
        """
        Append a new credit request row to the CSV.

        Args:
            request: CreditLimitRequest with final status (aprovado or rejeitado).

        Raises:
            FileNotFoundError: if the CSV file does not exist.
        """
        if not self._path.exists():
            raise FileNotFoundError(f"CSV file not found: {self._path}")

        timestamp = request.data_hora_solicitacao
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        tmp_path = self._path.with_suffix(".csv.tmp")
        lock_path = self._path.with_suffix(".csv.lock")
        try:
            with portalocker.Lock(str(lock_path), mode="w", timeout=_LOCK_TIMEOUT):
                with open(self._path, newline="", encoding="utf-8") as fh:
                    reader = csv.DictReader(fh)
                    if list(reader.fieldnames or []) != _EXPECTED_HEADER:
                        raise ValueError(
                            f"Unexpected CSV header: {reader.fieldnames}. "
                            f"Expected: {_EXPECTED_HEADER}"
                        )
                    existing_rows = list(reader)

                new_row = {
                    "cpf_cliente": str(request.cpf_cliente),
                    "data_hora_solicitacao": timestamp,
                    "limite_atual": str(request.limite_atual),
                    "novo_limite_solicitado": str(request.novo_limite_solicitado),
                    "status_pedido": request.status_pedido.value,
                }

                buf = io.StringIO()
                writer = csv.DictWriter(
                    buf, fieldnames=_EXPECTED_HEADER, lineterminator="\n"
                )
                writer.writeheader()
                writer.writerows(existing_rows)
                writer.writerow(new_row)
                tmp_path.write_text(buf.getvalue(), encoding="utf-8")

                # Validate .tmp — ADR-007 steps 5-7: header, columns, row shape
                _valid_statuses = {"pendente", "aprovado", "rejeitado"}
                with open(tmp_path, newline="", encoding="utf-8") as fh:
                    tmp_reader = csv.DictReader(fh)
                    if list(tmp_reader.fieldnames or []) != _EXPECTED_HEADER:
                        raise ValueError(
                            f".tmp header mismatch: {tmp_reader.fieldnames}"
                        )
                    check = list(tmp_reader)
                expected_count = len(existing_rows) + 1
                if len(check) != expected_count:
                    raise ValueError(
                        f".tmp row count {len(check)} != expected {expected_count}"
                    )
                for chk_row in check:
                    for col in _EXPECTED_HEADER:
                        if col not in chk_row:
                            raise ValueError(
                                f".tmp missing column {col!r} in row: {chk_row!r}"
                            )
                last = check[-1]
                if last["status_pedido"] not in _valid_statuses:
                    raise ValueError(
                        f".tmp last row has invalid status_pedido: "
                        f"{last['status_pedido']!r}"
                    )

                os.replace(tmp_path, self._path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
