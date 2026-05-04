"""Graph integration tests for credit interview happy-path orchestration."""

from __future__ import annotations

from app.graph.dependencies import GraphDependencies
from app.graph.graph_builder import build_graph
from app.schemas.common import Intent, InternalInterviewStep, InterviewOfferResponse
from app.schemas.credit import CreditInterviewData, EmploymentType
from app.services.score_service import ScoreService
from tests.conftest import (
    ANA,
    CARLOS,
    MARINA,
    FakeCreditRequestRepository,
    FakeCustomerRepository,
    FakeExchangeProvider,
    FakeIntentClassifier,
    FakeScoreLimitRepository,
)


def _cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _deps() -> tuple[GraphDependencies, FakeCustomerRepository]:
    customer_repo = FakeCustomerRepository([ANA, CARLOS, MARINA])
    deps = GraphDependencies(
        customer_repository=customer_repo,
        score_limit_repository=FakeScoreLimitRepository(),
        credit_request_repository=FakeCreditRequestRepository(),
        exchange_provider=FakeExchangeProvider(rate=5.2),
        intent_classifier=FakeIntentClassifier(Intent.CREDIT_INCREASE),
    )
    return deps, customer_repo


def test_rejected_credit_offer_acceptance_enters_interview_without_same_turn_loop() -> None:
    deps, _customer_repo = _deps()
    graph = build_graph(deps, interrupt_before=["credit_node"])
    config = _cfg("graph-interview-accept")

    # Turn 1: authenticate and stop before credit_node.
    state = graph.invoke(
        {
            "session_id": "graph-interview-accept",
            "trace_id": "trace-graph-interview-accept",
            "cpf_candidate": ANA.cpf,
            "birth_date_candidate": ANA.data_nascimento,
            "last_user_input": "quero aumentar meu limite",
        },
        config=config,
    )
    assert state.get("authenticated") is True

    # Turn 2: emulate rejected request awaiting confirmation, then accept with "sim".
    graph.update_state(
        config,
        {
            "current_state": "OFFERING_CREDIT_INTERVIEW",
            "request_rejected": True,
            "interview_offer_response": InterviewOfferResponse.UNKNOWN,
            "last_user_input": "sim",
        },
        as_node="credit_node",
    )
    state = dict(graph.invoke(None, config=config))

    assert state["current_state"] == "CREDIT_INTERVIEW_IN_PROGRESS"
    assert state["interview_step"] == InternalInterviewStep.INCOME
    assert "renda" in state["last_assistant_output"].lower()


def test_interview_completion_updates_score_and_stops_after_completion_message() -> None:
    deps, customer_repo = _deps()
    graph = build_graph(deps, interrupt_before=["credit_node"])
    config = _cfg("graph-interview-complete")

    expected_score = ScoreService.calculate(
        CreditInterviewData(
            renda_mensal=12000.0,
            tipo_emprego=EmploymentType.FORMAL,
            despesas_fixas_mensais=3000.0,
            numero_dependentes=0,
            tem_dividas_ativas=False,
        )
    ).score

    # Turn 1: authenticate and stop before credit_node.
    graph.invoke(
        {
            "session_id": "graph-interview-complete",
            "trace_id": "trace-graph-interview-complete",
            "cpf_candidate": ANA.cpf,
            "birth_date_candidate": ANA.data_nascimento,
            "last_user_input": "quero aumentar meu limite",
        },
        config=config,
    )

    # Turn 2: emulate interview at final step and finish with "não".
    graph.update_state(
        config,
        {
            "current_state": "CREDIT_INTERVIEW_IN_PROGRESS",
            "request_rejected": True,
            "interview_offer_response": InterviewOfferResponse.ACCEPTED,
            "interview_step": InternalInterviewStep.DEBTS,
            "interview_data": {
                "renda_mensal": 12000.0,
                "tipo_emprego": EmploymentType.FORMAL,
                "despesas_fixas_mensais": 3000.0,
                "numero_dependentes": 0,
            },
            "last_user_input": "não",
        },
        as_node="credit_interview_node",
    )
    state = dict(graph.invoke(None, config=config))

    assert state["current_state"] == "RECALCULATING_SCORE"
    assert state["interview_complete"] is True
    assert state["interview_data"] == {}
    assert "score" in state["last_assistant_output"].lower()

    stored = customer_repo.find_by_cpf(ANA.cpf)
    assert stored is not None
    assert stored.score_atual == expected_score
