"""
Phase 6C.2 — Full mocked flow integration tests.

Tests validate end-to-end graph flows using only in-memory fakes.
No LLM, no CSV, no network, no FastAPI.

Multi-turn strategy:
  The graph is compiled with interrupt_before=["intent_node"] for tests that
  need to check intermediate state after authentication. Each user "turn"
  corresponds to one .invoke() call:
    - Turn 1: graph.invoke(initial_state) — runs to interrupt
    - Turn N: graph.update_state(config, updates) + graph.invoke(None)

  Tests that naturally terminate (auth failure, circuit-breaker) use a
  single invoke() without interrupts.

Source of truth: STATE_MACHINE.md sections 3–4, TEST_PLAN.md section 3.2.
"""

import pytest

from app.graph.dependencies import GraphDependencies
from app.graph.graph_builder import build_graph
from app.schemas.common import Intent, InternalInterviewStep, InterviewOfferResponse
from app.schemas.credit import CreditRequestStatus, EmploymentType
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


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_deps(
    classifier_result: Intent = Intent.CREDIT_LIMIT,
    exchange_rate: float = 5.0,
    exchange_fail: bool = False,
) -> tuple[GraphDependencies, FakeCreditRequestRepository, FakeCustomerRepository]:
    """Build a full set of fakes. Returns (deps, credit_repo, customer_repo)."""
    customer_repo = FakeCustomerRepository([ANA, CARLOS, MARINA])
    credit_repo = FakeCreditRequestRepository()
    deps = GraphDependencies(
        customer_repository=customer_repo,
        score_limit_repository=FakeScoreLimitRepository(),
        credit_request_repository=credit_repo,
        exchange_provider=FakeExchangeProvider(
            rate=exchange_rate, should_fail=exchange_fail
        ),
        intent_classifier=FakeIntentClassifier(classifier_result),
    )
    return deps, credit_repo, customer_repo


def _cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _first_invoke(graph, session_id: str, trace_id: str, thread_id: str, **extra) -> dict:
    """
    First turn: provide credentials so triage_node can authenticate.
    Returns state after authentication (graph interrupted before intent_node).
    """
    state = {
        "session_id": session_id,
        "trace_id": trace_id,
        **extra,
    }
    return dict(graph.invoke(state, config=_cfg(thread_id)))


def _resume(graph, thread_id: str, **state_updates) -> dict:
    """
    Subsequent turn: update state with new user input then resume.
    Returns state after the next interrupt or END.
    """
    if state_updates:
        graph.update_state(_cfg(thread_id), state_updates)
    state = dict(graph.invoke(None, config=_cfg(thread_id)))
    for _ in range(3):
        if state.get("current_state") != "AUTHENTICATED":
            break
        state = dict(graph.invoke(None, config=_cfg(thread_id)))
    return state


# ── 1. Auth success → credit limit flow ──────────────────────────────────────


class TestFullAuthSuccessThenCreditLimitFlow:

    def test_auth_success_shows_credit_limit(self):
        """
        Multi-turn flow: start → triage (auth) [interrupt] → intent(CREDIT_LIMIT)
        → credit_node (SHOWING_CREDIT_LIMIT) [interrupt].

        Turn 1: provide CPF + birth_date → authenticate → interrupt before intent_node.
        Turn 2: provide last_user_input → intent_node → credit_node → interrupt.
        Expected: authenticated=True, current_customer set, current_state==SHOWING_CREDIT_LIMIT.
        """
        deps, _, _ = _make_deps(classifier_result=Intent.CREDIT_LIMIT)
        graph = build_graph(deps, interrupt_before=["intent_node"])

        # Turn 1: authenticate
        state1 = _first_invoke(
            graph,
            session_id="flow-auth-01",
            trace_id="trace-auth-01",
            thread_id="flow-auth-01-thread",
            cpf_candidate=ANA.cpf,
            birth_date_candidate=ANA.data_nascimento,
        )
        assert state1.get("authenticated") is True, (
            f"Expected authenticated=True after triage, got: {state1.get('authenticated')}"
        )
        assert state1.get("current_customer") is not None

        # Turn 2: send intent → credit_node shows limit → interrupt before intent_node
        state2 = _resume(
            graph,
            "flow-auth-01-thread",
            last_user_input="Quero ver meu limite de crédito",
        )
        assert state2.get("current_state") == "SHOWING_CREDIT_LIMIT", (
            f"Expected SHOWING_CREDIT_LIMIT, got: {state2.get('current_state')!r}"
        )
        output = state2.get("last_assistant_output", "")
        assert isinstance(output, str) and len(output) > 0, (
            "last_assistant_output must be a non-empty string"
        )
        # Output must mention the limit value in some numeric form (5000 or 5,000)
        assert "5" in output, (
            f"Response should mention ANA's limit: {output!r}"
        )


# ── 2. Auth failure blocks after three attempts ───────────────────────────────


class TestFullAuthFailureBlocksAfterThreeAttempts:

    def test_third_failed_attempt_ends_session(self):
        """
        STATE_MACHINE.md §3.2 Case E: auth_attempts=2 + one more failure
        → is_blocked=True, ended=True, graph reaches END.

        Single invoke — naturally terminates at ending_node.
        """
        deps, _, _ = _make_deps()
        graph = build_graph(deps)

        result = graph.invoke(
            {
                "session_id": "flow-block-01",
                "trace_id": "trace-block-01",
                "cpf_candidate": ANA.cpf,
                "birth_date_candidate": "1999-01-01",  # wrong birth date
                "auth_attempts": 2,
            },
            config=_cfg("flow-block-01-thread"),
        )

        assert result.get("is_blocked") is True or result.get("ended") is True, (
            "Session must be blocked or ended after 3 failed auth attempts. "
            f"Got: is_blocked={result.get('is_blocked')}, ended={result.get('ended')}"
        )
        assert result.get("current_state") in ("ENDED",), (
            f"Expected ENDED state, got: {result.get('current_state')!r}"
        )


# ── 3. Credit increase approved flow ─────────────────────────────────────────


class TestFullCreditIncreaseApprovedFlow:

    def test_credit_increase_request_approved_stored_in_repo(self):
        """
        STATE_MACHINE.md §3.4: authenticated user requests credit increase.
        Request is evaluated and approved → credit_request_repository.append called.

        ANA score=720 → max allowed=10000. Requesting 8000 → APPROVED.

        Turn 1: authenticate.
        Turn 2: provide intent + pre-populated credit_request → APPROVED.
        """
        deps, credit_repo, _ = _make_deps(classifier_result=Intent.CREDIT_INCREASE)
        graph = build_graph(deps, interrupt_before=["intent_node"])

        # Turn 1: authenticate
        state1 = _first_invoke(
            graph,
            session_id="flow-credit-01",
            trace_id="trace-credit-01",
            thread_id="flow-credit-01-thread",
            cpf_candidate=ANA.cpf,
            birth_date_candidate=ANA.data_nascimento,
        )
        assert state1.get("authenticated") is True

        # Turn 2: provide intent + credit_request (pre-populated to skip asking step)
        state2 = _resume(
            graph,
            "flow-credit-01-thread",
            last_user_input="Quero aumentar meu limite",
            credit_request={
                "cpf_cliente": ANA.cpf,
                "data_hora_solicitacao": "2026-05-01T10:00:00",
                "limite_atual": 5000.0,
                "novo_limite_solicitado": 8000.0,
                "status_pedido": "pendente",
            },
        )

        assert state2.get("current_state") == "CREDIT_REQUEST_APPROVED", (
            f"Expected CREDIT_REQUEST_APPROVED, got: {state2.get('current_state')!r}"
        )
        assert state2.get("request_rejected") is False
        assert len(credit_repo.appended) >= 1, (
            "credit_request_repository must have received the request via append()"
        )


# ── 4. Credit rejected → interview → score updated ───────────────────────────


class TestFullCreditRejectedThenInterviewUpdatesScore:

    def test_interview_updates_score_on_completion(self):
        """
        STATE_MACHINE.md §3.4 Case I + §3.5 completion.

        Strategy: compile with interrupt_before=["credit_node"] so we can
        inject a simulated credit rejection via update_state(as_node="credit_node")
        and provide a fully-collected interview state to credit_interview_node.

        Turn 1: authenticate → interrupt before credit_node (via intent routing).
        Turn 2: update_state(as_node="credit_node") with rejection + ACCEPTED offer +
                full interview_data at DEBTS step + last_user_input="não".
                Invoke → credit_interview_node runs (DEBTS → completes) →
                routes to credit_node → interrupt before credit_node.
        Expected: interview_complete=True, current_customer.score_atual updated,
                  customer_repo reflects new score.
        """
        deps, _, customer_repo = _make_deps(
            classifier_result=Intent.CREDIT_INCREASE
        )
        graph = build_graph(deps, interrupt_before=["credit_node"])
        config = _cfg("flow-interview-01-thread")

        # Turn 1: auth → intent_node(CREDIT_INCREASE) → interrupt before credit_node
        state1 = graph.invoke(
            {
                "session_id": "flow-interview-01",
                "trace_id": "trace-interview-01",
                "cpf_candidate": ANA.cpf,
                "birth_date_candidate": ANA.data_nascimento,
                "last_user_input": "Quero aumentar meu limite",
            },
            config=config,
        )
        assert state1.get("authenticated") is True, (
            f"Authentication must succeed in turn 1, got: {state1}"
        )

        # Turn 2: simulate credit_node rejection + ACCEPTED interview offer
        # + full interview data at DEBTS step.
        # update_state(as_node="credit_node") applies as if credit_node returned
        # these values, so route_after_credit(ACCEPTED) routes to credit_interview_node.
        graph.update_state(
            config,
            {
                "request_rejected": True,
                "interview_offer_response": InterviewOfferResponse.ACCEPTED,
                "interview_step": InternalInterviewStep.DEBTS,
                "last_user_input": "não",
                "interview_data": {
                    "renda_mensal": 6000.0,
                    "tipo_emprego": EmploymentType.FORMAL,
                    "despesas_fixas_mensais": 2000.0,
                    "numero_dependentes": 1,
                },
            },
            as_node="credit_node",
        )
        # Resume: credit_interview_node runs (DEBTS step "não") → completes →
        # routes to credit_node → interrupt before credit_node.
        state2 = _resume(graph, "flow-interview-01-thread")

        assert state2.get("interview_complete") is True, (
            f"interview_complete must be True. Got: {state2.get('interview_complete')}"
        )
        updated = state2.get("current_customer")
        assert updated is not None, "current_customer must be set after interview"
        score = (
            updated.score_atual
            if hasattr(updated, "score_atual")
            else updated.get("score_atual") if isinstance(updated, dict) else None
        )
        assert isinstance(score, int), f"score_atual must be an int, got {score!r}"
        assert 0 <= score <= 1000, f"Score {score} out of valid range [0, 1000]"

        # Repository must reflect the updated score
        stored = customer_repo.find_by_cpf(ANA.cpf)
        assert stored is not None
        assert stored.score_atual == score, (
            f"Repo score {stored.score_atual} must match state score {score}"
        )


# ── 5. Exchange quote flow ────────────────────────────────────────────────────


class TestFullExchangeQuoteFlow:

    def test_exchange_quote_returned_and_provider_called(self):
        """
        STATE_MACHINE.md §3.6: authenticated user requests exchange quote.
        FakeExchangeProvider is called once → EXCHANGE_SHOWING_QUOTE.

        Turn 1: authenticate.
        Turn 2: provide intent + exchange_request → exchange_node → quote shown.
        """
        exchange_provider = FakeExchangeProvider(rate=5.75)
        customer_repo = FakeCustomerRepository([ANA, CARLOS, MARINA])
        deps = GraphDependencies(
            customer_repository=customer_repo,
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=FakeCreditRequestRepository(),
            exchange_provider=exchange_provider,
            intent_classifier=FakeIntentClassifier(Intent.EXCHANGE_QUOTE),
        )
        graph = build_graph(deps, interrupt_before=["intent_node"])
        config = _cfg("flow-exchange-01-thread")

        # Turn 1: authenticate
        state1 = graph.invoke(
            {
                "session_id": "flow-exchange-01",
                "trace_id": "trace-exchange-01",
                "cpf_candidate": ANA.cpf,
                "birth_date_candidate": ANA.data_nascimento,
            },
            config=config,
        )
        assert state1.get("authenticated") is True

        # Turn 2: provide intent + exchange_request → exchange_node → quote
        graph.update_state(
            config,
            {
                "last_user_input": "Quero cotação de USD",
                "exchange_request": {
                    "base_currency": "BRL",
                    "target_currency": "USD",
                    "amount": 1000.0,
                },
            },
        )
        state2 = graph.invoke(None, config=config)

        assert state2.get("current_state") == "EXCHANGE_SHOWING_QUOTE", (
            f"Expected EXCHANGE_SHOWING_QUOTE, got: {state2.get('current_state')!r}"
        )
        assert len(exchange_provider.calls) >= 1, (
            "FakeExchangeProvider.get_quote must have been called at least once"
        )
        assert exchange_provider.calls[0] == ("BRL", "USD"), (
            f"Provider must be called with (BRL, USD), got: {exchange_provider.calls}"
        )


# ── 6. Unknown intent circuit-breaker ────────────────────────────────────────


class TestFullUnknownIntentCircuitBreaker:

    def test_third_unknown_intent_routes_to_ending(self):
        """
        STATE_MACHINE.md §3.3 Case D: unknown_intent_count reaches 3 →
        routes to ending_node, session ends.

        Pre-sets unknown_intent_count=2 + authenticated=True bypass so the
        graph goes directly: start → triage → intent_node(UNKNOWN, count→3)
        → ending_node → END.

        Single invoke — naturally terminates.
        """
        deps, _, _ = _make_deps(classifier_result=Intent.UNKNOWN)
        graph = build_graph(deps)

        result = graph.invoke(
            {
                "session_id": "flow-unknown-01",
                "trace_id": "trace-unknown-01",
                "authenticated": True,
                "current_customer": ANA.model_dump(),
                "unknown_intent_count": 2,
                "last_user_input": "bla bla bla qualquer coisa",
            },
            config=_cfg("flow-unknown-01-thread"),
        )

        assert result.get("ended") is True, (
            f"Session must be ended. ended={result.get('ended')}, "
            f"current_state={result.get('current_state')!r}"
        )
        assert result.get("unknown_intent_count") >= 3, (
            f"unknown_intent_count must be ≥ 3, got: {result.get('unknown_intent_count')}"
        )
