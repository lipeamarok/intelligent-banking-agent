"""Unit tests for RegistrationService and CustomerRepository.create_customer."""

import csv
import io
import tempfile
from pathlib import Path

import pytest

from app.repositories.customer_repository import CustomerRepository, DuplicateCpfError
from app.repositories.score_limit_repository import ScoreLimitRepository
from app.schemas.customer import Customer
from app.services.registration_service import RegistrationService

# ── Fixtures ─────────────────────────────────────────────────────────────────

_CLIENTES_SEED = (
    "cpf,data_nascimento,nome,score_atual,limite_credito\n"
    "12345678901,1990-05-12,Ana Silva,720,5000.00\n"
)

_SCORE_LIMITE_SEED = (
    "score_minimo,score_maximo,limite_maximo_permitido\n"
    "0,299,1000.00\n"
    "300,499,2500.00\n"
    "500,699,5000.00\n"
    "700,849,10000.00\n"
    "850,1000,20000.00\n"
)


@pytest.fixture
def tmp_clientes(tmp_path: Path) -> Path:
    p = tmp_path / "clientes.csv"
    p.write_text(_CLIENTES_SEED, encoding="utf-8")
    return p


@pytest.fixture
def tmp_score_limite(tmp_path: Path) -> Path:
    p = tmp_path / "score_limite.csv"
    p.write_text(_SCORE_LIMITE_SEED, encoding="utf-8")
    return p


@pytest.fixture
def customer_repo(tmp_clientes: Path) -> CustomerRepository:
    return CustomerRepository(tmp_clientes)


@pytest.fixture
def score_repo(tmp_score_limite: Path) -> ScoreLimitRepository:
    return ScoreLimitRepository(tmp_score_limite)


# ── CustomerRepository.create_customer ───────────────────────────────────────

class TestCreateCustomer:
    def test_create_appends_row(self, customer_repo: CustomerRepository):
        new = Customer(
            cpf="99988877766",
            data_nascimento="2000-01-15",
            nome="Novo Cliente",
            score_atual=300,
            limite_credito=2500.00,
        )
        customer_repo.create_customer(new)
        found = customer_repo.find_by_cpf("99988877766")
        assert found is not None
        assert found.nome == "Novo Cliente"
        assert found.score_atual == 300
        assert found.limite_credito == 2500.00

    def test_create_raises_on_duplicate_cpf(self, customer_repo: CustomerRepository):
        duplicate = Customer(
            cpf="12345678901",  # already in seed
            data_nascimento="1990-05-12",
            nome="Ana Silva Copia",
            score_atual=300,
            limite_credito=2500.00,
        )
        with pytest.raises(DuplicateCpfError):
            customer_repo.create_customer(duplicate)

    def test_create_preserves_existing_rows(self, customer_repo: CustomerRepository):
        new = Customer(
            cpf="11122233344",
            data_nascimento="1995-03-20",
            nome="Pedro Teste",
            score_atual=300,
            limite_credito=2500.00,
        )
        customer_repo.create_customer(new)
        # Original row still present
        original = customer_repo.find_by_cpf("12345678901")
        assert original is not None
        assert original.nome == "Ana Silva"

    def test_create_raises_if_csv_missing(self, tmp_path: Path):
        repo = CustomerRepository(tmp_path / "nonexistent.csv")
        customer = Customer(
            cpf="11111111111",
            data_nascimento="1990-01-01",
            nome="Ghost",
            score_atual=300,
            limite_credito=2500.00,
        )
        with pytest.raises(FileNotFoundError):
            repo.create_customer(customer)


# ── RegistrationService ───────────────────────────────────────────────────────

class TestRegistrationService:
    def test_register_creates_customer_with_initial_score(
        self, customer_repo: CustomerRepository, score_repo: ScoreLimitRepository
    ):
        customer = RegistrationService.register_new_customer(
            name="Maria Nunes",
            cpf="55566677788",
            birth_date="1998-07-22",
            customer_repository=customer_repo,
            score_limit_repository=score_repo,
        )
        assert customer.cpf == "55566677788"
        assert customer.nome == "Maria Nunes"
        assert customer.score_atual == 300
        assert customer.limite_credito == 2500.00  # score 300 maps to 2500.00

    def test_register_persists_to_csv(
        self, customer_repo: CustomerRepository, score_repo: ScoreLimitRepository
    ):
        RegistrationService.register_new_customer(
            name="Bruno Lima",
            cpf="44455566677",
            birth_date="1985-11-30",
            customer_repository=customer_repo,
            score_limit_repository=score_repo,
        )
        found = customer_repo.find_by_cpf("44455566677")
        assert found is not None
        assert found.nome == "Bruno Lima"

    def test_register_raises_on_duplicate_cpf(
        self, customer_repo: CustomerRepository, score_repo: ScoreLimitRepository
    ):
        with pytest.raises(DuplicateCpfError):
            RegistrationService.register_new_customer(
                name="Ana Duplicada",
                cpf="12345678901",  # exists in seed
                birth_date="1990-05-12",
                customer_repository=customer_repo,
                score_limit_repository=score_repo,
            )

    def test_register_raises_on_blank_name(
        self, customer_repo: CustomerRepository, score_repo: ScoreLimitRepository
    ):
        with pytest.raises(ValueError, match="name must not be blank"):
            RegistrationService.register_new_customer(
                name="   ",
                cpf="77788899900",
                birth_date="1990-01-01",
                customer_repository=customer_repo,
                score_limit_repository=score_repo,
            )

    def test_register_raises_on_invalid_cpf(
        self, customer_repo: CustomerRepository, score_repo: ScoreLimitRepository
    ):
        with pytest.raises(ValueError, match="cpf must be 11 digits"):
            RegistrationService.register_new_customer(
                name="Nome Válido",
                cpf="123",  # too short
                birth_date="1990-01-01",
                customer_repository=customer_repo,
                score_limit_repository=score_repo,
            )
