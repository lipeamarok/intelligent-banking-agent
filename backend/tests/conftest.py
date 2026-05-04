"""
Shared pytest fixtures and test helpers for Phase 3 TDD Zero.

Provides:
- CSV file fixtures using tmp_path (no real data files touched).
- Sample data constants matching TEST_PLAN.md section 5.
- In-memory fake repositories for service unit tests.
- GraphState factory helper.
"""

from pathlib import Path

import pytest

from app.schemas.common import Intent
from app.schemas.credit import CreditLimitRequest, CreditRequestStatus, EmploymentType
from app.schemas.customer import Customer
from app.graph.state import GraphState

# ── Sample data (TEST_PLAN.md section 5.1 and 5.2) ────────────────────────────

SAMPLE_CUSTOMERS_CSV = (
    "cpf,data_nascimento,nome,score_atual,limite_credito\n"
    "12345678901,1990-05-12,Ana Silva,720,5000.00\n"
    "98765432100,1985-11-20,Carlos Souza,540,2500.00\n"
    "11122233344,2000-01-01,Marina Lima,250,800.00\n"
)

SAMPLE_SCORE_LIMIT_CSV = (
    "score_minimo,score_maximo,limite_maximo_permitido\n"
    "0,299,1000.00\n"
    "300,499,2500.00\n"
    "500,699,5000.00\n"
    "700,849,10000.00\n"
    "850,1000,20000.00\n"
)

EMPTY_CREDIT_REQUESTS_CSV = (
    "cpf_cliente,data_hora_solicitacao,limite_atual,novo_limite_solicitado,status_pedido\n"
)

# ── CSV file fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def customers_csv(tmp_path: Path) -> Path:
    """Temporary clientes.csv with 3 sample customers. No real data touched."""
    p = tmp_path / "clientes.csv"
    p.write_text(SAMPLE_CUSTOMERS_CSV, encoding="utf-8")
    return p


@pytest.fixture()
def score_limit_csv(tmp_path: Path) -> Path:
    """Temporary score_limite.csv with standard score/limit table."""
    p = tmp_path / "score_limite.csv"
    p.write_text(SAMPLE_SCORE_LIMIT_CSV, encoding="utf-8")
    return p


@pytest.fixture()
def credit_requests_csv(tmp_path: Path) -> Path:
    """Temporary solicitacoes_aumento_limite.csv with header only (empty)."""
    p = tmp_path / "solicitacoes_aumento_limite.csv"
    p.write_text(EMPTY_CREDIT_REQUESTS_CSV, encoding="utf-8")
    return p


# ── Sample Customer objects ────────────────────────────────────────────────────

ANA = Customer(
    cpf="12345678901",
    data_nascimento="1990-05-12",
    nome="Ana Silva",
    score_atual=720,
    limite_credito=5000.00,
)

CARLOS = Customer(
    cpf="98765432100",
    data_nascimento="1985-11-20",
    nome="Carlos Souza",
    score_atual=540,
    limite_credito=2500.00,
)

MARINA = Customer(
    cpf="11122233344",
    data_nascimento="2000-01-01",
    nome="Marina Lima",
    score_atual=250,
    limite_credito=800.00,
)


# ── In-memory fake repositories ────────────────────────────────────────────────


class FakeCustomerRepository:
    """
    In-memory replacement for CustomerRepository.
    Allows AuthService and CreditService unit tests to run without CSV files.
    """

    def __init__(self, customers: list[Customer]) -> None:
        self._store: dict[str, Customer] = {c.cpf: c for c in customers}

    def find_by_cpf(self, cpf: str) -> Customer | None:
        return self._store.get(cpf)

    def update_score(self, cpf: str, new_score: int) -> None:
        if cpf not in self._store:
            raise KeyError(f"CPF not found: {cpf}")
        original = self._store[cpf]
        self._store[cpf] = Customer(
            cpf=original.cpf,
            data_nascimento=original.data_nascimento,
            nome=original.nome,
            score_atual=new_score,
            limite_credito=original.limite_credito,
        )

    def update_limit(self, cpf: str, new_limit: float) -> None:
        if cpf not in self._store:
            raise KeyError(f"CPF not found: {cpf}")
        if new_limit < 0 or new_limit > 1_000_000:
            raise ValueError(
                f"new_limit must be in [0, 1_000_000], got {new_limit}"
            )
        original = self._store[cpf]
        self._store[cpf] = Customer(
            cpf=original.cpf,
            data_nascimento=original.data_nascimento,
            nome=original.nome,
            score_atual=original.score_atual,
            limite_credito=float(new_limit),
        )

    def create_customer(self, customer: Customer) -> None:
        from app.repositories.customer_repository import DuplicateCpfError
        if customer.cpf in self._store:
            raise DuplicateCpfError(customer.cpf)
        self._store[customer.cpf] = customer


class FakeScoreLimitRepository:
    """
    In-memory replacement for ScoreLimitRepository.
    Returns max allowed limit based on score range table (TEST_PLAN.md section 5.2).
    """

    _TABLE = [
        (0, 299, 1000.0),
        (300, 499, 2500.0),
        (500, 699, 5000.0),
        (700, 849, 10000.0),
        (850, 1000, 20000.0),
    ]

    def find_max_limit_for_score(self, score: int) -> float:
        for low, high, max_limit in self._TABLE:
            if low <= score <= high:
                return max_limit
        raise ValueError(f"No score range found for score={score}")


class FakeCreditRequestRepository:
    """
    In-memory replacement for CreditRequestRepository.
    Tracks appended requests so tests can assert persistence without CSV.
    """

    def __init__(self) -> None:
        self.appended: list[CreditLimitRequest] = []

    def append(self, request: CreditLimitRequest) -> None:
        self.appended.append(request)


class FakeIntentClassifier:
    """
    Deterministic intent classifier stub for intent_node tests.
    Records all classify() calls so tests can assert the classifier was invoked.
    Returns a pre-configured result regardless of input.
    """

    def __init__(self, result: Intent) -> None:
        self.result = result
        self.calls: list[str] = []

    def classify(self, message: str) -> Intent:
        self.calls.append(message)
        return self.result


class FakeExchangeProvider:
    """
    Deterministic exchange provider stub for exchange_node tests.
    Records all get_quote() calls. Can be configured to fail on demand.
    """

    def __init__(self, rate: float = 5.0, should_fail: bool = False) -> None:
        self.rate = rate
        self.should_fail = should_fail
        self.calls: list[tuple[str, str]] = []

    def get_quote(self, base_currency: str, target_currency: str) -> dict:
        self.calls.append((base_currency, target_currency))
        if self.should_fail:
            raise RuntimeError("provider unavailable")
        return {
            "base_currency": base_currency,
            "target_currency": target_currency,
            "rate": self.rate,
            "timestamp": "2026-05-01T00:00:00Z",
            "provider": "fake",
        }


class FakeResponseInterpreter:
    """Deterministic constrained interpreter stub for normalization fallback tests."""

    def __init__(self, mapping: dict[tuple[str, str], str] | None = None) -> None:
        self.mapping = mapping or {}
        self.calls: list[tuple[str, str]] = []

    def interpret_choice(
        self,
        *,
        user_message: str,
        field_name: str,
        allowed_values: list[str],
        guidance: str,
        examples: dict[str, str] | None = None,
    ) -> str | None:
        del allowed_values, guidance, examples
        key = (field_name, user_message)
        self.calls.append(key)
        return self.mapping.get(key)


# ── GraphState factory ─────────────────────────────────────────────────────────


def make_graph_state(**overrides) -> GraphState:
    """
    Build a GraphState with sensible test defaults.
    Override any field by passing keyword arguments.
    """
    defaults: dict = {
        "session_id": "test-session-001",
        "trace_id": "test-trace-001",
    }
    defaults.update(overrides)
    return GraphState(**defaults)
