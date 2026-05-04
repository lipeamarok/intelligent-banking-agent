"""
Unit tests for CSV repositories.

Source of truth: REQUIREMENTS.md FR-AUTH-004, FR-CREDIT-004, FR-INTERVIEW-008,
                  TEST_PLAN.md sections 5 and 6.6.

All tests use tmp_path — no production or demo CSV files are touched.
"""

from pathlib import Path

import pytest

from app.repositories.customer_repository import CustomerRepository
from app.repositories.credit_request_repository import CreditRequestRepository
from app.repositories.score_limit_repository import ScoreLimitRepository
from app.schemas.credit import CreditLimitRequest, CreditRequestStatus
from tests.conftest import (
    SAMPLE_CUSTOMERS_CSV,
    SAMPLE_SCORE_LIMIT_CSV,
    EMPTY_CREDIT_REQUESTS_CSV,
)


# ── CustomerRepository ─────────────────────────────────────────────────────────


class TestCustomerRepository:

    def test_find_by_cpf_returns_correct_customer(self, customers_csv: Path):
        """TC-REPO-001: repository must find customer by exact CPF string."""
        repo = CustomerRepository(customers_csv)
        customer = repo.find_by_cpf("12345678901")
        assert customer is not None
        assert customer.cpf == "12345678901"
        assert customer.nome == "Ana Silva"

    def test_find_by_cpf_preserves_cpf_as_string(self, customers_csv: Path):
        """TC-AUTH-004: CPF must be read as string, never cast to int."""
        repo = CustomerRepository(customers_csv)
        customer = repo.find_by_cpf("12345678901")
        assert isinstance(customer.cpf, str)

    def test_find_by_cpf_returns_none_for_unknown_cpf(self, customers_csv: Path):
        """TC-REPO-002: missing CPF must return None, not raise exception."""
        repo = CustomerRepository(customers_csv)
        result = repo.find_by_cpf("00000000000")
        assert result is None

    def test_find_all_three_customers(self, customers_csv: Path):
        """All sample customers must be findable."""
        repo = CustomerRepository(customers_csv)
        assert repo.find_by_cpf("12345678901") is not None
        assert repo.find_by_cpf("98765432100") is not None
        assert repo.find_by_cpf("11122233344") is not None

    def test_read_returns_correct_score(self, customers_csv: Path):
        repo = CustomerRepository(customers_csv)
        customer = repo.find_by_cpf("12345678901")
        assert customer.score_atual == 720

    def test_read_returns_correct_limit(self, customers_csv: Path):
        repo = CustomerRepository(customers_csv)
        customer = repo.find_by_cpf("98765432100")
        assert customer.limite_credito == 2500.00

    def test_update_score_persists_new_value(self, customers_csv: Path):
        """FR-INTERVIEW-008: updated score must be readable back from CSV."""
        repo = CustomerRepository(customers_csv)
        repo.update_score("12345678901", 850)
        updated = repo.find_by_cpf("12345678901")
        assert updated.score_atual == 850

    def test_update_score_preserves_header(self, customers_csv: Path):
        """TC-REPO-004: CSV header must survive score update."""
        repo = CustomerRepository(customers_csv)
        repo.update_score("12345678901", 800)
        content = customers_csv.read_text(encoding="utf-8")
        assert content.startswith("cpf,data_nascimento,nome,score_atual,limite_credito")

    def test_update_score_does_not_mutate_other_customers(self, customers_csv: Path):
        """Updating one row must not change other rows."""
        repo = CustomerRepository(customers_csv)
        repo.update_score("12345678901", 900)
        carlos = repo.find_by_cpf("98765432100")
        assert carlos.score_atual == 540  # unchanged

    def test_update_score_uses_atomic_write(self, customers_csv: Path):
        """
        TC-REPO-004: atomic write means .tmp file is created and then replaces
        the original. After a successful update, no orphan .tmp file must remain.
        """
        repo = CustomerRepository(customers_csv)
        repo.update_score("12345678901", 800)
        tmp_file = customers_csv.with_suffix(".csv.tmp")
        assert not tmp_file.exists(), ".tmp file must be cleaned up after atomic write"

    def test_raises_on_missing_file(self, tmp_path: Path):
        """FileNotFoundError when CSV does not exist."""
        repo = CustomerRepository(tmp_path / "nonexistent.csv")
        with pytest.raises(FileNotFoundError):
            repo.find_by_cpf("12345678901")

    def test_raises_on_corrupted_csv(self, tmp_path: Path):
        """Corrupted CSV must raise a controlled exception, not crash silently."""
        bad_csv = tmp_path / "clientes.csv"
        bad_csv.write_text("not,valid\ncorrupted;;;data\n", encoding="utf-8")
        repo = CustomerRepository(bad_csv)
        with pytest.raises(Exception):
            repo.find_by_cpf("12345678901")


# ── ScoreLimitRepository ──────────────────────────────────────────────────────


class TestScoreLimitRepository:

    def test_find_max_limit_for_low_score(self, score_limit_csv: Path):
        """Score 250 → 0–299 range → max_limit 1000.00."""
        repo = ScoreLimitRepository(score_limit_csv)
        limit = repo.find_max_limit_for_score(250)
        assert limit == 1000.00

    def test_find_max_limit_for_mid_score(self, score_limit_csv: Path):
        """Score 540 → 500–699 range → max_limit 5000.00."""
        repo = ScoreLimitRepository(score_limit_csv)
        limit = repo.find_max_limit_for_score(540)
        assert limit == 5000.00

    def test_find_max_limit_for_high_score(self, score_limit_csv: Path):
        """Score 720 → 700–849 range → max_limit 10000.00."""
        repo = ScoreLimitRepository(score_limit_csv)
        limit = repo.find_max_limit_for_score(720)
        assert limit == 10000.00

    def test_find_max_limit_for_top_score(self, score_limit_csv: Path):
        """Score 900 → 850–1000 range → max_limit 20000.00."""
        repo = ScoreLimitRepository(score_limit_csv)
        limit = repo.find_max_limit_for_score(900)
        assert limit == 20000.00

    def test_find_max_limit_for_boundary_score_zero(self, score_limit_csv: Path):
        """Score 0 must match first range."""
        repo = ScoreLimitRepository(score_limit_csv)
        limit = repo.find_max_limit_for_score(0)
        assert limit == 1000.00

    def test_find_max_limit_for_boundary_score_1000(self, score_limit_csv: Path):
        """Score 1000 must match last range."""
        repo = ScoreLimitRepository(score_limit_csv)
        limit = repo.find_max_limit_for_score(1000)
        assert limit == 20000.00

    def test_raises_on_missing_file(self, tmp_path: Path):
        repo = ScoreLimitRepository(tmp_path / "nonexistent.csv")
        with pytest.raises(FileNotFoundError):
            repo.find_max_limit_for_score(500)

    def test_raises_on_score_below_zero(self, score_limit_csv: Path):
        """REQUIREMENTS.md §7.2: score range is 0-1000. -1 is invalid input."""
        repo = ScoreLimitRepository(score_limit_csv)
        with pytest.raises(ValueError):
            repo.find_max_limit_for_score(-1)

    def test_raises_on_score_above_1000(self, score_limit_csv: Path):
        """REQUIREMENTS.md §7.2: score range is 0-1000. 1001 is invalid input."""
        repo = ScoreLimitRepository(score_limit_csv)
        with pytest.raises(ValueError):
            repo.find_max_limit_for_score(1001)

    def test_rejects_non_canonical_header_name(self, tmp_path: Path):
        bad = tmp_path / "score_limite.csv"
        bad.write_text(
            "score_minimo,score_maximo,limite_maximo\n"
            "700,849,10000.00\n",
            encoding="utf-8",
        )
        repo = ScoreLimitRepository(bad)
        with pytest.raises(ValueError, match="Unexpected CSV header"):
            repo.find_max_limit_for_score(720)


# ── CreditRequestRepository ───────────────────────────────────────────────────


class TestCreditRequestRepository:

    def test_append_adds_row_to_csv(self, credit_requests_csv: Path):
        """TC-REPO-003: appending a request adds exactly one row."""
        repo = CreditRequestRepository(credit_requests_csv)
        request = CreditLimitRequest(
            cpf_cliente="12345678901",
            data_hora_solicitacao="2026-05-01T12:00:00",
            limite_atual=5000.0,
            novo_limite_solicitado=8000.0,
            status_pedido=CreditRequestStatus.APROVADO,
        )
        repo.append(request)

        content = credit_requests_csv.read_text(encoding="utf-8")
        lines = [l for l in content.strip().splitlines() if l]
        assert len(lines) == 2  # header + 1 data row

    def test_append_preserves_header(self, credit_requests_csv: Path):
        """TC-REPO-003: header must remain unchanged after append."""
        repo = CreditRequestRepository(credit_requests_csv)
        request = CreditLimitRequest(
            cpf_cliente="12345678901",
            data_hora_solicitacao="2026-05-01T12:00:00",
            limite_atual=5000.0,
            novo_limite_solicitado=8000.0,
            status_pedido=CreditRequestStatus.APROVADO,
        )
        repo.append(request)

        first_line = credit_requests_csv.read_text(encoding="utf-8").splitlines()[0]
        assert first_line == (
            "cpf_cliente,data_hora_solicitacao,limite_atual,"
            "novo_limite_solicitado,status_pedido"
        )

    def test_append_persists_cpf_as_string(self, credit_requests_csv: Path):
        """CPF must be written as string — leading zeros must be preserved."""
        repo = CreditRequestRepository(credit_requests_csv)
        request = CreditLimitRequest(
            cpf_cliente="01234567890",
            data_hora_solicitacao="2026-05-01T12:00:00",
            limite_atual=1000.0,
            novo_limite_solicitado=2000.0,
            status_pedido=CreditRequestStatus.REJEITADO,
        )
        repo.append(request)

        content = credit_requests_csv.read_text(encoding="utf-8")
        assert "01234567890" in content

    def test_append_multiple_requests(self, credit_requests_csv: Path):
        """Multiple appends must result in multiple rows without overwriting."""
        repo = CreditRequestRepository(credit_requests_csv)
        for i in range(3):
            request = CreditLimitRequest(
                cpf_cliente="12345678901",
                data_hora_solicitacao=f"2026-05-01T1{i}:00:00",
                limite_atual=5000.0,
                novo_limite_solicitado=float(6000 + i * 1000),
                status_pedido=CreditRequestStatus.APROVADO,
            )
            repo.append(request)

        content = credit_requests_csv.read_text(encoding="utf-8")
        lines = [l for l in content.strip().splitlines() if l]
        assert len(lines) == 4  # header + 3 rows

    def test_append_uses_atomic_write(self, credit_requests_csv: Path):
        """
        TC-REPO-004: atomic write must not leave orphan .tmp files.
        """
        repo = CreditRequestRepository(credit_requests_csv)
        request = CreditLimitRequest(
            cpf_cliente="12345678901",
            data_hora_solicitacao="2026-05-01T12:00:00",
            limite_atual=5000.0,
            novo_limite_solicitado=8000.0,
            status_pedido=CreditRequestStatus.APROVADO,
        )
        repo.append(request)
        tmp = credit_requests_csv.with_suffix(".csv.tmp")
        assert not tmp.exists()

    def test_raises_on_missing_file(self, tmp_path: Path):
        """FileNotFoundError when CSV does not exist."""
        repo = CreditRequestRepository(tmp_path / "nonexistent.csv")
        request = CreditLimitRequest(
            cpf_cliente="12345678901",
            limite_atual=5000.0,
            novo_limite_solicitado=8000.0,
        )
        with pytest.raises(FileNotFoundError):
            repo.append(request)
