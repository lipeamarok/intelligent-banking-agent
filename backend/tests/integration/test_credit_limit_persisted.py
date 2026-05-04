"""
Integration: approved credit increase persists the new limite_credito on the
customer repository (P1 hotfix).
"""

from __future__ import annotations

from app.graph.dependencies import GraphDependencies
from app.graph.graph_builder import build_graph
from app.schemas.common import Intent
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


class TestCreditIncreasePersistsLimit:
    def test_approved_increase_writes_new_limit_to_customer_repository(self) -> None:
        customer_repo = FakeCustomerRepository([ANA, CARLOS, MARINA])
        credit_repo = FakeCreditRequestRepository()
        deps = GraphDependencies(
            customer_repository=customer_repo,
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=credit_repo,
            exchange_provider=FakeExchangeProvider(rate=5.0),
            intent_classifier=FakeIntentClassifier(Intent.CREDIT_INCREASE),
        )

        original_limit = customer_repo.find_by_cpf(ANA.cpf).limite_credito  # type: ignore[union-attr]

        graph = build_graph(deps, interrupt_before=["intent_node"])

        # Turn 1: authenticate
        state1 = dict(
            graph.invoke(
                {
                    "session_id": "credit-persist-01",
                    "trace_id": "credit-persist-01",
                    "cpf_candidate": ANA.cpf,
                    "birth_date_candidate": ANA.data_nascimento,
                },
                config=_cfg("credit-persist-01-thread"),
            )
        )
        assert state1.get("authenticated") is True

        # Turn 2: pre-populate credit_request to short-circuit the ASKING step
        graph.update_state(
            _cfg("credit-persist-01-thread"),
            {
                "last_user_input": "Quero aumentar meu limite",
                "credit_request": {
                    "cpf_cliente": ANA.cpf,
                    "data_hora_solicitacao": "2026-05-01T10:00:00",
                    "limite_atual": original_limit,
                    "novo_limite_solicitado": 8000.0,
                    "status_pedido": "pendente",
                },
            },
        )
        state2 = dict(graph.invoke(None, config=_cfg("credit-persist-01-thread")))
        # Drain any AUTHENTICATED bounce
        for _ in range(3):
            if state2.get("current_state") != "AUTHENTICATED":
                break
            state2 = dict(graph.invoke(None, config=_cfg("credit-persist-01-thread")))

        assert state2.get("current_state") == "CREDIT_REQUEST_APPROVED"
        # Persisted via repository
        persisted = customer_repo.find_by_cpf(ANA.cpf)
        assert persisted is not None
        assert persisted.limite_credito == 8000.0
        # current_customer in state reflects new limit too
        cc = state2.get("current_customer")
        if hasattr(cc, "limite_credito"):
            assert cc.limite_credito == 8000.0
        elif isinstance(cc, dict):
            assert cc.get("limite_credito") == 8000.0
