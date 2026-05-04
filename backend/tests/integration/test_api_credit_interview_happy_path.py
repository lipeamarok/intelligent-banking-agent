"""Integration tests for credit interview flow over POST /api/v1/chat."""

from __future__ import annotations

import csv
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.dependencies import get_app_graph
from app.bootstrap.dependencies import create_repositories
from app.graph.dependencies import GraphDependencies
from app.graph.graph_builder import build_graph
from app.llm.intent_classifier import IntentClassifier
from app.llm.manager import LLMManager
from app.llm.mock_provider import MockProvider
from app.main import create_app
from app.schemas.credit import CreditInterviewData, EmploymentType
from app.services.score_service import ScoreService
from tests.conftest import FakeResponseInterpreter


def _write_seed_csvs(base: Path) -> None:
    (base / "clientes.csv").write_text(
        "cpf,data_nascimento,nome,score_atual,limite_credito\n"
        "12345678901,1990-05-12,Ana Silva,720,5000.00\n"
        "98765432100,1985-10-03,Carlos Souza,580,2500.00\n"
        "45678912300,1998-02-20,Marina Costa,830,12000.00\n",
        encoding="utf-8",
    )
    (base / "score_limite.csv").write_text(
        "score_minimo,score_maximo,limite_maximo_permitido\n"
        "0,299,1000.00\n"
        "300,499,2500.00\n"
        "500,699,5000.00\n"
        "700,849,10000.00\n"
        "850,1000,20000.00\n",
        encoding="utf-8",
    )
    (base / "solicitacoes_aumento_limite.csv").write_text(
        "cpf_cliente,data_hora_solicitacao,limite_atual,novo_limite_solicitado,status_pedido\n",
        encoding="utf-8",
    )


def _build_test_client(
    tmp_path: Path,
    response_interpreter: FakeResponseInterpreter | None = None,
) -> tuple[TestClient, Path, MockProvider]:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_seed_csvs(data_dir)

    repos = create_repositories(data_dir)
    provider = MockProvider(content="credit_increase")
    classifier = IntentClassifier(LLMManager(primary_provider=provider))
    deps = GraphDependencies(
        customer_repository=repos.customer_repository,
        score_limit_repository=repos.score_limit_repository,
        credit_request_repository=repos.credit_request_repository,
        exchange_provider=None,
        intent_classifier=classifier,
        response_interpreter=response_interpreter,
    )

    graph = build_graph(deps)
    app = create_app()
    app.dependency_overrides[get_app_graph] = lambda: graph
    return TestClient(app), data_dir, provider


def _chat(client: TestClient, message: str, session_id: str | None = None) -> dict:
    payload = {"message": message}
    if session_id is not None:
        payload["session_id"] = session_id
    response = client.post("/api/v1/chat", json=payload)
    assert response.status_code == 200
    return response.json()


def _read_score(clientes_csv: Path, cpf: str) -> int:
    with open(clientes_csv, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row["cpf"] == cpf:
                return int(row["score_atual"])
    raise AssertionError(f"CPF not found in clientes.csv: {cpf}")


def test_rejected_credit_offer_accepts_interview_and_starts_questions(tmp_path: Path) -> None:
    client, _data_dir, _provider = _build_test_client(tmp_path)

    turn1 = _chat(client, "olá")
    sid = turn1["session_id"]

    _chat(client, "12345678901", sid)
    _chat(client, "12-05-1990", sid)
    _chat(client, "quero aumentar meu limite", sid)

    offered = _chat(client, "20000", sid)
    assert offered["state"] == "OFFERING_CREDIT_INTERVIEW"
    assert offered["agent"] == "credit"
    assert offered["ended"] is False

    accepted = _chat(client, "sim", sid)
    assert accepted["state"] == "CREDIT_INTERVIEW_IN_PROGRESS"
    assert accepted["agent"] == "credit_interview"
    assert accepted["ended"] is False
    assert "renda" in accepted["reply"].lower()


def test_credit_interview_happy_path_recalculates_and_persists_score(tmp_path: Path) -> None:
    client, data_dir, provider = _build_test_client(tmp_path)

    expected_score = ScoreService.calculate(
        CreditInterviewData(
            renda_mensal=12000.0,
            tipo_emprego=EmploymentType.FORMAL,
            despesas_fixas_mensais=3000.0,
            numero_dependentes=0,
            tem_dividas_ativas=False,
        )
    ).score

    start = _chat(client, "olá")
    sid = start["session_id"]

    _chat(client, "12345678901", sid)
    _chat(client, "12-05-1990", sid)
    _chat(client, "quero aumentar meu limite", sid)
    _chat(client, "20000", sid)
    _chat(client, "sim", sid)
    _chat(client, "12000", sid)
    _chat(client, "formal", sid)
    _chat(client, "3000", sid)
    _chat(client, "0", sid)
    done = _chat(client, "não", sid)

    assert done["state"] == "RECALCULATING_SCORE"
    assert done["agent"] == "credit_interview"
    assert done["ended"] is False
    assert "score" in done["reply"].lower()

    ana_score = _read_score(data_dir / "clientes.csv", "12345678901")
    assert ana_score == expected_score
    assert ana_score != 720

    # LLM should classify intent once (credit increase). Interview turns are deterministic.
    assert len(provider.requests) == 1


def test_credit_interview_declined_does_not_start_interview(tmp_path: Path) -> None:
    client, _data_dir, _provider = _build_test_client(tmp_path)

    start = _chat(client, "olá")
    sid = start["session_id"]

    _chat(client, "12345678901", sid)
    _chat(client, "12-05-1990", sid)
    _chat(client, "quero aumentar meu limite", sid)
    _chat(client, "20000", sid)                 # → OFFERING_CREDIT_INTERVIEW
    declined = _chat(client, "não", sid)        # decline interview

    assert declined["state"] == "IDENTIFYING_INTENT"
    assert declined["agent"] == "triage"
    assert declined["ended"] is False
    assert "tudo bem" in declined["reply"].lower()


def test_post_interview_ok_reassesses_same_request(tmp_path: Path) -> None:
    interpreter = FakeResponseInterpreter({("confirmation", "ok"): "accepted"})
    client, data_dir, _provider = _build_test_client(tmp_path, response_interpreter=interpreter)

    start = _chat(client, "olá")
    sid = start["session_id"]

    _chat(client, "12345678901", sid)
    _chat(client, "12-05-1990", sid)
    _chat(client, "quero aumentar meu limite", sid)
    _chat(client, "20000", sid)
    _chat(client, "sim", sid)  # accept interview
    _chat(client, "2000", sid)
    _chat(client, "formal", sid)
    _chat(client, "1000", sid)
    _chat(client, "nenhum", sid)
    _chat(client, "não", sid)
    reassessed = _chat(client, "ok", sid)

    assert reassessed["state"] == "CREDIT_REQUEST_REJECTED"
    assert reassessed["agent"] == "credit"
    assert reassessed["ended"] is False
    assert "permanece" in reassessed["reply"].lower()

    with open(data_dir / "solicitacoes_aumento_limite.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    assert len(rows) == 2
    assert rows[-1]["status_pedido"] == "rejeitado"
