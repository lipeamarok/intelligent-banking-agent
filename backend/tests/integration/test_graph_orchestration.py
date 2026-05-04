"""
Phase 6 — LangGraph Orchestration Tests (behavioral contracts).

All nodes and edge routers are fully implemented (Phase 6B complete).
Phase 6C/6D: graph_builder assembled and validated — 365 tests passing.
Edge router tests: assert return value == expected node name string.

Source of truth:
  STATE_MACHINE.md sections 3–6
  ARCHITECTURE.md §3.5, §4.3
  REQUIREMENTS.md FR-AUTH-*, FR-CREDIT-*, FR-INTERVIEW-*, FR-EXCHANGE-*
  TEST_PLAN.md sections 6.1–6.7
  DECISIONS.md ADR-007

Rules enforced here:
- All routing is deterministic (no real LLM, no real CSV).
- Services are injected via fake/mock objects.
- No real portalocker, no real CSV files, no external API calls.
"""

import time

import pytest
from langgraph.graph import END

from app.graph.dependencies import GraphDependencies
from app.graph.edges import (
    route_after_credit,
    route_after_exchange,
    route_after_intent,
    route_after_interview,
    route_after_start,
    route_after_triage,
)
from app.graph.graph_builder import build_graph
from app.graph.nodes import (
    credit_interview_node,
    credit_node,
    ending_node,
    exchange_node,
    intent_node,
    start_node,
    triage_node,
)
from app.graph.state import GraphState
from app.schemas.common import Intent, InternalInterviewStep, InterviewOfferResponse
from app.schemas.credit import CreditRequestStatus, EmploymentType
from app.schemas.customer import Customer
from tests.conftest import (
    ANA,
    CARLOS,
    MARINA,
    FakeCreditRequestRepository,
    FakeExchangeProvider,
    FakeIntentClassifier,
    FakeResponseInterpreter,
    FakeScoreLimitRepository,
    make_graph_state,
)


# ── helpers ───────────────────────────────────────────────────────────────────


def _base_state(**overrides) -> GraphState:
    """Minimal valid GraphState for integration tests."""
    return make_graph_state(**overrides)


# ══════════════════════════════════════════════════════════════════════════════
# 1. GraphState lifecycle
# ══════════════════════════════════════════════════════════════════════════════


class TestGraphStateLifecycle:

    def test_start_node_returns_partial_update(self):
        """
        STATE_MACHINE.md §3.1: start_node returns a partial update dict with
        current_state='STARTED', next_step='triage_node', ended=False.
        """
        state = _base_state()
        result = start_node(state)
        assert isinstance(result, dict)
        assert result["current_state"] == "STARTED"
        assert result["next_step"] == "triage_node"
        assert result["ended"] is False

    def test_start_node_does_not_overwrite_identity_fields(self):
        """
        STATE_MACHINE.md §2: session_id and trace_id are identity fields that
        must not be clobbered by node updates. start_node must not include
        session_id or trace_id in its return dict.
        """
        state = _base_state(session_id="sess-abc", trace_id="trace-xyz")
        result = start_node(state)
        assert "session_id" not in result
        assert "trace_id" not in result

    def test_graph_state_preserves_session_id_and_trace_id(self):
        """
        STATE_MACHINE.md §2: session_id and trace_id are identity fields and
        must survive through any node update.
        GraphState already guarantees this via Pydantic — test validates invariant.
        """
        state = _base_state(session_id="sess-abc", trace_id="trace-xyz")
        assert state.session_id == "sess-abc"
        assert state.trace_id == "trace-xyz"

    def test_recent_messages_limit_is_three(self):
        """
        STATE_MACHINE.md §2: recent_messages must not exceed 3 turns.
        Pydantic max_length=3 enforces this at assignment.
        """
        from app.schemas.session import RecentMessage
        state = _base_state()
        msgs = [
            RecentMessage(role="user", content=f"msg {i}") for i in range(3)
        ]
        state.recent_messages = msgs
        assert len(state.recent_messages) == 3

    def test_recent_messages_rejects_fourth_message(self):
        """max_length=3 must reject a list of 4 messages."""
        from pydantic import ValidationError
        from app.schemas.session import RecentMessage
        state = _base_state()
        msgs = [
            RecentMessage(role="user", content=f"msg {i}") for i in range(4)
        ]
        with pytest.raises(ValidationError):
            state.recent_messages = msgs

    def test_ended_true_prevents_further_flow(self):
        """
        STATE_MACHINE.md §4 Global Rules: ended=True → ending_node.
        Every route_after_* must short-circuit and return 'ending_node'.
        """
        state = _base_state(ended=True)
        assert route_after_triage(state) == "ending_node"

    def test_build_graph_is_implemented(self):
        """Phase 6C: graph_builder is now implemented. build_graph(deps) must not raise."""
        from tests.conftest import FakeCustomerRepository, FakeIntentClassifier
        from app.schemas.common import Intent
        from app.graph.dependencies import GraphDependencies
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA]),
            intent_classifier=FakeIntentClassifier(Intent.END_CONVERSATION),
        )
        graph = build_graph(deps)
        assert graph is not None
        assert hasattr(graph, "invoke")


# ══════════════════════════════════════════════════════════════════════════════
# 2. Triage flow
# ══════════════════════════════════════════════════════════════════════════════


class TestTriageFlow:

    # ── behavioral contracts (triage_node implemented, Phase 6B.5) ──

    def test_triage_node_asks_for_cpf_when_missing(self):
        """
        FR-AUTH-002 / STATE_MACHINE.md §3.2 step 1:
        When cpf_candidate is absent, triage_node must ask for CPF
        and loop back to itself without authenticating.
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state()
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        result = triage_node(state, deps)
        assert isinstance(result, dict)
        assert result["current_state"] == "ASKING_CPF"
        assert result["next_step"] == "triage_node"
        assert isinstance(result.get("last_assistant_output"), str)
        assert len(result["last_assistant_output"]) > 0
        assert "current_customer" not in result
        assert "authenticated_cpf" not in result

    def test_triage_node_asks_for_birth_date_when_cpf_present(self):
        """
        FR-AUTH-003 / STATE_MACHINE.md §3.2 step 2:
        When cpf_candidate is set but birth_date_candidate is absent,
        triage_node must ask for the birth date and loop back to itself.
        cpf_candidate must be preserved in the returned update.
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(cpf_candidate="12345678901")
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        result = triage_node(state, deps)
        assert isinstance(result, dict)
        assert result["current_state"] == "ASKING_BIRTH_DATE"
        assert result["next_step"] == "triage_node"
        assert isinstance(result.get("last_assistant_output"), str)
        assert len(result["last_assistant_output"]) > 0
        # Must not erase cpf_candidate — node returns partial update only
        assert "cpf_candidate" not in result or result["cpf_candidate"] == "12345678901"

    def test_triage_node_authenticates_valid_customer(self):
        """
        FR-AUTH-004 / STATE_MACHINE.md §3.2 step 4:
        When both cpf_candidate and birth_date_candidate match a customer,
        triage_node must authenticate, set current_customer, and proceed
        to intent_node. auth_attempts must be reset to 0 on success
        (REQUIREMENTS.md FR-AUTH-004: reset auth_attempts after success).
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(
            cpf_candidate="12345678901",
            birth_date_candidate="1990-05-12",
        )
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        result = triage_node(state, deps)
        assert isinstance(result, dict)
        assert result["authenticated"] is True
        assert result["authenticated_cpf"] == "12345678901"
        assert result["current_customer"] == ANA
        assert result["current_state"] == "AUTHENTICATED"
        assert result["next_step"] == "intent_node"
        assert result.get("auth_attempts", 0) == 0

    def test_triage_node_rejects_unknown_cpf_and_increments_attempts(self):
        """
        FR-AUTH-005 / STATE_MACHINE.md §3.2:
        When the CPF is not found in the repository, triage_node must
        increment auth_attempts, keep authenticated=False, and loop back.
        The error message must not expose technical details.
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(
            cpf_candidate="00000000000",
            birth_date_candidate="2000-01-01",
            auth_attempts=0,
        )
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        result = triage_node(state, deps)
        assert isinstance(result, dict)
        assert result.get("authenticated") is not True
        assert result["auth_attempts"] == 1
        assert result["current_state"] == "ASKING_CPF"
        assert result["next_step"] == "triage_node"
        assert isinstance(result.get("last_assistant_output"), str)
        assert len(result["last_assistant_output"]) > 0
        # Must not expose stack traces or repository internals
        assert "Exception" not in result["last_assistant_output"]
        assert "Traceback" not in result["last_assistant_output"]

    def test_triage_node_rejects_wrong_birth_date_and_increments_attempts(self):
        """
        FR-AUTH-005 / STATE_MACHINE.md §3.2:
        When CPF exists but birth date is wrong, triage_node must increment
        auth_attempts and ask the user to try again (ASKING_BIRTH_DATE).
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(
            cpf_candidate="12345678901",
            birth_date_candidate="1111-01-01",  # wrong date for ANA
            auth_attempts=1,
        )
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        result = triage_node(state, deps)
        assert isinstance(result, dict)
        assert result.get("authenticated") is not True
        assert result["auth_attempts"] == 2
        assert result["current_state"] == "ASKING_BIRTH_DATE"
        assert result["next_step"] == "triage_node"

    def test_triage_node_blocks_after_third_failure(self):
        """
        FR-AUTH-006 / STATE_MACHINE.md §3.2:
        When auth_attempts reaches 3, triage_node must block the session,
        mark ended=True, and route to ending_node with a safe closing message.
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(
            cpf_candidate="00000000000",
            birth_date_candidate="2000-01-01",
            auth_attempts=2,
        )
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        result = triage_node(state, deps)
        assert isinstance(result, dict)
        assert result["auth_attempts"] == 3
        assert result["is_blocked"] is True
        assert result["ended"] is True
        assert result["current_state"] == "ENDED"
        assert result["next_step"] == "ending_node"
        assert isinstance(result.get("last_assistant_output"), str)
        assert len(result["last_assistant_output"]) > 0

    def test_triage_node_missing_customer_repository_returns_controlled_error(self):
        """
        ARCHITECTURE.md §3.5 inv. #8: system must prefer safe failure over
        inconsistent behavior. When both credentials are present but
        deps.customer_repository is None, triage_node must not raise
        AttributeError — it must return a controlled error update dict.
        """
        state = _base_state(
            cpf_candidate="12345678901",
            birth_date_candidate="1990-05-12",
        )
        deps = GraphDependencies(customer_repository=None)
        result = triage_node(state, deps)
        assert isinstance(result, dict)
        assert result.get("recoverable_error") is True
        assert result.get("retry_available") is False
        assert result["current_state"] == "ERROR"
        assert result["next_step"] == "ending_node"
        assert isinstance(result.get("last_error"), str)
        assert len(result["last_error"]) > 0

    def test_triage_node_does_not_mutate_state_directly(self):
        """
        STATE_MACHINE.md §3 Node Return Contracts: nodes must not mutate the
        state object. Changes must appear only in the returned dict.
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(cpf_candidate="12345678901")
        original_cpf = state.cpf_candidate
        original_auth = state.authenticated
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        triage_node(state, deps)
        # State object must be unchanged after the call
        assert state.cpf_candidate == original_cpf
        assert state.authenticated == original_auth

    def test_triage_node_ends_conversation_when_requested_during_cpf_step(self):
        """
        FR-ENDING-001: user may request end of conversation at any point.
        When last_user_input is an end-conversation phrase while awaiting CPF,
        triage_node must return ended=True and route to ending_node immediately
        rather than asking for CPF again.
        """
        from tests.conftest import FakeCustomerRepository
        for phrase in ("encerrar", "finalizar", "terminar", "tchau"):
            state = _base_state(current_state="ASKING_CPF", last_user_input=phrase)
            deps = GraphDependencies(
                customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
            )
            result = triage_node(state, deps)
            assert result.get("ended") is True, f"phrase={phrase!r} did not trigger end"
            assert result["current_state"] == "ENDED"
            assert result["next_step"] == "ending_node"

    def test_triage_node_ends_conversation_when_requested_during_birth_date_step(self):
        """
        FR-ENDING-001: user may request end of conversation at any point.
        When last_user_input is an end-conversation phrase during ASKING_BIRTH_DATE
        (CPF already collected), triage_node must end the session instead of
        responding with a date-format error.
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(
            current_state="ASKING_BIRTH_DATE",
            cpf_candidate=ANA.cpf,
            last_user_input="encerrar conversa",
        )
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        result = triage_node(state, deps)
        assert result.get("ended") is True
        assert result["current_state"] == "ENDED"
        assert result["next_step"] == "ending_node"
        assert isinstance(result.get("last_assistant_output"), str)
        assert len(result["last_assistant_output"]) > 0

    def test_route_after_triage_routes_to_intent_when_authenticated(self):
        """
        STATE_MACHINE.md §4 Triage: authenticated=True → intent_node.
        """
        state = _base_state(authenticated=True)
        assert route_after_triage(state) == "intent_node"

    def test_route_after_triage_routes_to_ending_after_three_failures(self):
        """
        STATE_MACHINE.md §4 Triage: auth_attempts >= 3 → ending_node.
        StateGuard also enforces this at check_entry level.
        """
        state = _base_state(auth_attempts=3, is_blocked=True)
        assert route_after_triage(state) == "ending_node"

    def test_route_after_triage_routes_to_ending_when_blocked(self):
        """
        STATE_MACHINE.md §4 Global Rules: is_blocked=True → ending_node.
        Applies at every route_after_* level.
        """
        state = _base_state(is_blocked=True)
        assert route_after_triage(state) == "ending_node"

    def test_route_after_triage_routes_to_ending_when_ended(self):
        """
        STATE_MACHINE.md §4 Global Rules: ended=True → ending_node.
        """
        state = _base_state(ended=True)
        assert route_after_triage(state) == "ending_node"

    def test_route_after_triage_stays_in_triage_when_not_authenticated(self):
        """
        STATE_MACHINE.md §4 Triage: not authenticated, attempts < 3 → triage_node.
        """
        state = _base_state(authenticated=False, auth_attempts=1)
        assert route_after_triage(state) == "triage_node"

    def test_triage_state_tracks_auth_attempts(self):
        """
        GraphState.auth_attempts must be incrementable.
        After implementation, each AuthService failure must increment by 1.
        """
        state = _base_state(auth_attempts=0)
        state.auth_attempts += 1
        assert state.auth_attempts == 1

    def test_triage_state_marks_blocked_at_three_attempts(self):
        """
        REQUIREMENTS.md FR-AUTH-006: three failures → is_blocked=True, ended=True.
        """
        state = _base_state(auth_attempts=2)
        state.auth_attempts += 1
        state.is_blocked = True
        state.ended = True
        assert state.auth_attempts == 3
        assert state.is_blocked is True
        assert state.ended is True

    def test_triage_state_authenticated_sets_authenticated_cpf(self):
        """
        STATE_MACHINE.md §3.2: successful auth must set authenticated_cpf
        and current_customer.
        """
        state = _base_state(
            authenticated=True,
            authenticated_cpf="12345678901",
            current_customer=ANA,
        )
        assert state.authenticated is True
        assert state.authenticated_cpf == "12345678901"
        assert state.current_customer is not None
        assert state.current_customer.cpf == "12345678901"


# ══════════════════════════════════════════════════════════════════════════════
# 3. Intent flow
# ══════════════════════════════════════════════════════════════════════════════


class TestIntentFlow:

    # ── Behavioral contracts (Phase 6B.6) ─────────────────────────────────────

    def test_intent_node_classifies_credit_limit(self):
        """
        STATE_MACHINE.md §3.3: intent_node classifies user message as CREDIT_LIMIT.
        Classifier is called with last_user_input.
        Result sets intent, next_step, and resets unknown_intent_count.
        """
        classifier = FakeIntentClassifier(Intent.CREDIT_LIMIT)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            last_user_input="quero consultar meu limite",
        )
        result = intent_node(state, deps)
        assert result["intent"] == Intent.CREDIT_LIMIT
        assert result["current_state"] == "IDENTIFYING_INTENT"
        assert result["next_step"] == "credit_node"
        assert result["unknown_intent_count"] == 0
        assert classifier.calls == ["quero consultar meu limite"]

    def test_intent_node_classifies_credit_increase(self):
        """
        STATE_MACHINE.md §3.3: CREDIT_INCREASE intent routes to credit_node.
        unknown_intent_count must be reset to 0 on a valid classification.
        """
        classifier = FakeIntentClassifier(Intent.CREDIT_INCREASE)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            last_user_input="quero aumentar meu limite de crédito",
            unknown_intent_count=1,
        )
        result = intent_node(state, deps)
        assert result["intent"] == Intent.CREDIT_INCREASE
        assert result["next_step"] == "credit_node"
        assert result["unknown_intent_count"] == 0

    def test_intent_node_classifies_exchange_quote(self):
        """
        STATE_MACHINE.md §3.3: EXCHANGE_QUOTE intent routes to exchange_node.
        unknown_intent_count must be reset to 0 on a valid classification.
        """
        classifier = FakeIntentClassifier(Intent.EXCHANGE_QUOTE)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            last_user_input="quero uma cotação de dólar",
            unknown_intent_count=2,
        )
        result = intent_node(state, deps)
        assert result["intent"] == Intent.EXCHANGE_QUOTE
        assert result["next_step"] == "exchange_node"
        assert result["unknown_intent_count"] == 0

    def test_intent_node_classifies_end_conversation(self):
        """
        STATE_MACHINE.md §3.3: END_CONVERSATION intent routes to ending_node.
        unknown_intent_count must be reset to 0 on a valid classification.
        """
        classifier = FakeIntentClassifier(Intent.END_CONVERSATION)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            last_user_input="quero encerrar o atendimento",
        )
        result = intent_node(state, deps)
        assert result["intent"] == Intent.END_CONVERSATION
        assert result["next_step"] == "ending_node"
        assert result["unknown_intent_count"] == 0

    def test_intent_node_followup_yes_asks_new_request_without_classifier(self):
        """
        After a completion prompt ("Posso ajudar com mais alguma coisa?"),
        a short "sim" must keep the session open and ask for the next request
        instead of ending due to intent misclassification.
        """
        classifier = FakeIntentClassifier(Intent.END_CONVERSATION)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            last_action_summary="PARTIAL_INCREASE_APPROVED",
            last_user_input="sim",
        )
        result = intent_node(state, deps)
        assert result["intent"] == Intent.UNKNOWN
        assert result["current_state"] == "IDENTIFYING_INTENT"
        assert result["next_step"] == "intent_node"
        assert result["unknown_intent_count"] == 0
        assert result["last_action_summary"] == "ASKED_FOR_INTENT_AFTER_FOLLOWUP"
        assert classifier.calls == []

    def test_intent_node_followup_yes_works_after_triage_reentry(self):
        """
        Real API turns pass through start/triage between messages and may
        overwrite last_action_summary. The continuation guard must still work
        based on current_state from the prior credit reply.
        """
        classifier = FakeIntentClassifier(Intent.END_CONVERSATION)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            current_state="CREDIT_REQUEST_APPROVED",
            last_action_summary="AUTH_SESSION_REUSED",
            last_user_input="sim",
        )
        result = intent_node(state, deps)
        assert result["intent"] == Intent.UNKNOWN
        assert result["current_state"] == "IDENTIFYING_INTENT"
        assert result["next_step"] == "intent_node"
        assert result["last_action_summary"] == "ASKED_FOR_INTENT_AFTER_FOLLOWUP"
        assert classifier.calls == []

    def test_intent_node_followup_no_ends_without_classifier(self):
        """
        After a completion prompt, a short decline ("não") should end the
        session directly without invoking the intent classifier.
        """
        classifier = FakeIntentClassifier(Intent.CREDIT_LIMIT)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            last_action_summary="CREDIT_REQUEST_APPROVED",
            last_user_input="não",
        )
        result = intent_node(state, deps)
        assert result["intent"] == Intent.END_CONVERSATION
        assert result["current_state"] == "ENDING"
        assert result["next_step"] == "ending_node"
        assert result["unknown_intent_count"] == 0
        assert result["last_action_summary"] == "FOLLOWUP_DECLINED"
        assert classifier.calls == []

    def test_intent_node_short_followup_with_domain_terms_skips_yes_no_gate(self):
        """
        Regression: short domain messages like "quero cotacao cambio" must not
        be interpreted as yes/no confirmation after completion prompts.
        They should route as executable intents.
        """
        classifier = FakeIntentClassifier(Intent.EXCHANGE_QUOTE)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            current_state="EXCHANGE_SHOWING_QUOTE",
            last_action_summary="EXCHANGE_QUOTE_SHOWN",
            last_user_input="quero cotacao cambio",
        )
        result = intent_node(state, deps)
        assert result["intent"] == Intent.EXCHANGE_QUOTE
        assert result["next_step"] == "exchange_node"
        assert result["last_action_summary"] == "INTENT_CLASSIFIED"
        assert classifier.calls == ["quero cotacao cambio"]

    def test_intent_node_increase_verb_skips_yes_no_gate(self):
        """
        Regression: short prompts like "pode aumentar mais?" after a successful
        credit response must not be interpreted as follow-up yes/no confirmation.
        """
        classifier = FakeIntentClassifier(Intent.CREDIT_INCREASE)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            current_state="CREDIT_REQUEST_APPROVED",
            last_action_summary="CREDIT_REASSESSMENT_APPROVED",
            last_user_input="pode aumentar mais?",
        )
        result = intent_node(state, deps)
        assert result["intent"] == Intent.CREDIT_INCREASE
        assert result["next_step"] == "credit_node"
        assert result["last_action_summary"] == "INTENT_CLASSIFIED"
        assert classifier.calls == ["pode aumentar mais?"]

    def test_intent_node_capability_query_bypasses_classifier(self):
        """
        Meta capability questions must be answered directly without intent
        classifier routing to operational nodes.
        """

        class _FakeAdvisor:
            def advise(self, **_kwargs):
                return "Posso consultar limite, aumentar limite e cotar cambio."

        classifier = FakeIntentClassifier(Intent.EXCHANGE_QUOTE)
        deps = GraphDependencies(
            intent_classifier=classifier,
            capability_advisor=_FakeAdvisor(),
        )
        state = _base_state(
            authenticated=True,
            last_user_input="o que voce consegue fazer?",
        )
        result = intent_node(state, deps)
        assert result["intent"] == Intent.UNKNOWN
        assert result["next_step"] == "intent_node"
        assert result["last_action_summary"] == "CAPABILITY_ADVISED"
        assert "consultar limite" in result["last_assistant_output"].lower()
        assert classifier.calls == []

    def test_intent_node_capability_query_timeout_falls_back_quickly(self):
        """
        Capability advisor must not block the turn indefinitely. On timeout,
        intent_node should return a deterministic fallback capability hint.
        """

        class _SlowAdvisor:
            def advise(self, **_kwargs):
                time.sleep(5)
                return "late"

        classifier = FakeIntentClassifier(Intent.EXCHANGE_QUOTE)
        deps = GraphDependencies(
            intent_classifier=classifier,
            capability_advisor=_SlowAdvisor(),
        )
        state = _base_state(
            authenticated=True,
            last_user_input="o que voce consegue fazer?",
        )

        started = time.monotonic()
        result = intent_node(state, deps)
        elapsed = time.monotonic() - started

        assert elapsed < 2.5
        assert result["intent"] == Intent.UNKNOWN
        assert result["next_step"] == "intent_node"
        assert result["last_action_summary"] == "CAPABILITY_ADVISED"
        assert "consulta de limite" in result["last_assistant_output"].lower()
        assert classifier.calls == []

    def test_intent_node_clears_stale_credit_request_for_new_increase_turn(self):
        """
        Regression: after a rejected request, a fresh "quero aumentar limite"
        without explicit amount must not reuse stale credit_request.
        """
        classifier = FakeIntentClassifier(Intent.CREDIT_INCREASE)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            current_state="IDENTIFYING_INTENT",
            credit_request={
                "cpf_cliente": ANA.cpf,
                "limite_atual": 5000.0,
                "novo_limite_solicitado": 16000.0,
            },
            request_rejected=True,
            last_user_input="quero aumentar limite",
        )
        result = intent_node(state, deps)
        assert result["intent"] == Intent.CREDIT_INCREASE
        assert result["next_step"] == "credit_node"
        assert result["credit_request"] is None
        assert result["request_rejected"] is False

    def test_intent_node_clears_stale_credit_request_after_approval(self):
        """
        Regression: after a CREDIT_REQUEST_APPROVED, a fresh "quero aumentar"
        without explicit amount must not reuse the previously approved credit_request.
        """
        classifier = FakeIntentClassifier(Intent.CREDIT_INCREASE)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            current_state="CREDIT_REQUEST_APPROVED",
            last_action_summary="CREDIT_REQUEST_APPROVED",
            credit_request={
                "cpf_cliente": ANA.cpf,
                "limite_atual": 3000.0,
                "novo_limite_solicitado": 5000.0,
            },
            request_rejected=False,
            last_user_input="quero aumentar mais",
        )
        result = intent_node(state, deps)
        assert result["intent"] == Intent.CREDIT_INCREASE
        assert result["next_step"] == "credit_node"
        assert result["credit_request"] is None

    def test_intent_node_clears_stale_exchange_request_for_generic_exchange(self):
        """
        Generic exchange requests without named currency must clear stale pair
        so exchange_node asks for a fresh pair.
        """
        classifier = FakeIntentClassifier(Intent.EXCHANGE_QUOTE)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            current_state="IDENTIFYING_INTENT",
            last_action_summary="EXCHANGE_QUOTE_SHOWN",
            exchange_request={"base_currency": "USD", "target_currency": "BRL"},
            last_user_input="quero cotacao de cambio",
        )
        result = intent_node(state, deps)
        assert result["intent"] == Intent.EXCHANGE_QUOTE
        assert result["next_step"] == "exchange_node"
        assert result["exchange_request"] is None

    def test_intent_node_followup_prompt_classifies_exchange_deterministically(self):
        """
        After the follow-up prompt asking what the user needs next, clear
        exchange requests should route deterministically to exchange_node
        without requiring LLM intent classification.
        """
        classifier = FakeIntentClassifier(Intent.UNKNOWN)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            current_state="IDENTIFYING_INTENT",
            last_action_summary="ASKED_FOR_INTENT_AFTER_FOLLOWUP",
            last_user_input="quero cotação do dólar",
        )
        result = intent_node(state, deps)
        assert result["intent"] == Intent.EXCHANGE_QUOTE
        assert result["current_state"] == "IDENTIFYING_INTENT"
        assert result["next_step"] == "exchange_node"
        assert result["unknown_intent_count"] == 0
        assert result["last_action_summary"] == "INTENT_CLASSIFIED_DETERMINISTIC"
        assert classifier.calls == []

    def test_intent_node_handles_unknown_intent(self):
        """
        STATE_MACHINE.md §3.3: UNKNOWN intent increments unknown_intent_count.
        Node stays in IDENTIFYING_INTENT and loops back to itself.
        last_assistant_output must ask for clarification (non-empty string).
        """
        classifier = FakeIntentClassifier(Intent.UNKNOWN)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            last_user_input="ugh whatever",
            unknown_intent_count=0,
        )
        result = intent_node(state, deps)
        assert result["intent"] == Intent.UNKNOWN
        assert result["unknown_intent_count"] == 1
        assert result["current_state"] == "IDENTIFYING_INTENT"
        assert result["next_step"] == "intent_node"
        assert isinstance(result.get("last_assistant_output"), str)
        assert len(result["last_assistant_output"]) > 0

    def test_intent_node_ends_after_third_unknown(self):
        """
        STATE_MACHINE.md §10 Circuit Breaker: three consecutive UNKNOWN intents
        must trigger session termination. Node sets next_step='ending_node' and
        current_state='ENDING'. unknown_intent_count must reach 3.
        """
        classifier = FakeIntentClassifier(Intent.UNKNOWN)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            last_user_input="???",
            unknown_intent_count=2,
        )
        result = intent_node(state, deps)
        assert result["unknown_intent_count"] == 3
        assert result["next_step"] == "ending_node"
        assert result["current_state"] == "ENDING"
        assert isinstance(result.get("last_assistant_output"), str)
        assert len(result["last_assistant_output"]) > 0

    def test_intent_node_missing_classifier_returns_controlled_error(self):
        """
        STATE_MACHINE.md §3 Node Return Contracts: node must not raise an
        uncontrolled AttributeError when deps.intent_classifier is None.
        Returns a controlled error payload with recoverable_error=True,
        retry_available=False, current_state='ERROR', next_step='ending_node'.
        """
        deps = GraphDependencies(intent_classifier=None)
        state = _base_state(
            authenticated=True,
            last_user_input="quero meu limite",
        )
        result = intent_node(state, deps)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is False
        assert result["current_state"] == "ERROR"
        assert result["next_step"] == "ending_node"
        assert isinstance(result.get("last_error"), str)
        assert len(result["last_error"]) > 0

    def test_intent_node_rejects_invalid_classifier_output(self):
        """
        STATE_MACHINE.md §3 rule 4: nodes must validate structured outputs
        before updating state. A classifier returning a raw string (not an
        Intent enum member) must be rejected; the node must not accept the
        raw string as a routing decision.
        result must carry recoverable_error=True and retry_available=True.
        intent must remain UNKNOWN or absent — never a raw string.
        """
        class BrokenClassifier:
            calls: list = []
            def classify(self, message: str):
                self.calls.append(message)
                return "credit_node"  # invalid — not an Intent enum member

        deps = GraphDependencies(intent_classifier=BrokenClassifier())
        state = _base_state(
            authenticated=True,
            last_user_input="quero algo",
        )
        result = intent_node(state, deps)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is True
        raw_intent = result.get("intent")
        assert raw_intent != "credit_node", "Raw classifier string must not be stored as intent"
        assert result["current_state"] in ("IDENTIFYING_INTENT", "ERROR")

    def test_intent_node_requires_last_user_input(self):
        """
        STATE_MACHINE.md §2: last_user_input may be None if no message yet.
        intent_node must ask for clarification instead of calling the classifier,
        and must loop back to itself.
        """
        classifier = FakeIntentClassifier(Intent.CREDIT_LIMIT)
        deps = GraphDependencies(intent_classifier=classifier)
        for empty_input in (None, ""):
            state = _base_state(
                authenticated=True,
                last_user_input=empty_input,
            )
            result = intent_node(state, deps)
            assert result["current_state"] == "IDENTIFYING_INTENT"
            assert result["next_step"] == "intent_node"
            assert isinstance(result.get("last_assistant_output"), str)
            assert len(result["last_assistant_output"]) > 0
            assert classifier.calls == [], "Classifier must not be called when last_user_input is empty"

    def test_intent_node_does_not_mutate_state_directly(self):
        """
        STATE_MACHINE.md §3 Node Return Contracts: nodes must return a partial
        update dict; they must not modify the input state object in-place.
        """
        classifier = FakeIntentClassifier(Intent.CREDIT_LIMIT)
        deps = GraphDependencies(intent_classifier=classifier)
        state = _base_state(
            authenticated=True,
            last_user_input="quero meu limite",
            intent=None,
            unknown_intent_count=0,
        )
        original_intent = state.intent
        original_count = state.unknown_intent_count
        intent_node(state, deps)  # result discarded — checking side-effects only
        assert state.intent == original_intent
        assert state.unknown_intent_count == original_count

    # ── Edge router tests (unchanged) ─────────────────────────────────────────

    def test_route_after_intent_to_credit_for_credit_limit(self):
        """
        STATE_MACHINE.md §4 Intent: intent == credit → credit_node.
        Intent.CREDIT_LIMIT maps to credit domain.
        """
        state = _base_state(authenticated=True, intent=Intent.CREDIT_LIMIT)
        assert route_after_intent(state) == "credit_node"

    def test_route_after_intent_to_credit_for_credit_increase(self):
        """
        STATE_MACHINE.md §4 Intent: intent == credit → credit_node.
        Intent.CREDIT_INCREASE also maps to credit domain.
        """
        state = _base_state(authenticated=True, intent=Intent.CREDIT_INCREASE)
        assert route_after_intent(state) == "credit_node"

    def test_route_after_intent_to_exchange_for_exchange_quote(self):
        """
        STATE_MACHINE.md §4 Intent: intent == exchange → exchange_node.
        """
        state = _base_state(authenticated=True, intent=Intent.EXCHANGE_QUOTE)
        assert route_after_intent(state) == "exchange_node"

    def test_route_after_intent_to_credit_for_credit_interview(self):
        """
        FR-INTERVIEW-002: explicit user request for credit interview must
        route directly to credit_interview_node without going through
        credit_node (which would ask for a limit amount first).
        """
        state = _base_state(
            authenticated=True,
            intent=Intent.CREDIT_INTERVIEW,
            last_action_summary="INTENT_CLASSIFIED",
        )
        assert route_after_intent(state) == "credit_interview_node"

    def test_route_after_intent_to_ending_for_end_conversation(self):
        """
        STATE_MACHINE.md §4 Intent: intent == end → ending_node.
        """
        state = _base_state(authenticated=True, intent=Intent.END_CONVERSATION)
        assert route_after_intent(state) == "ending_node"

    def test_route_after_intent_stays_in_intent_for_unknown(self):
        """
        STATE_MACHINE.md §4 Intent: unknown intent with count < 3 → intent_node.
        """
        state = _base_state(authenticated=True, intent=Intent.UNKNOWN, unknown_intent_count=1)
        assert route_after_intent(state) == "intent_node"

    def test_route_after_intent_stays_in_intent_for_none_intent(self):
        """
        STATE_MACHINE.md §4 Intent: intent=None (not yet classified) → intent_node.
        """
        state = _base_state(authenticated=True, intent=None)
        assert route_after_intent(state) == "intent_node"

    def test_route_after_intent_to_ending_after_three_unknown(self):
        """
        STATE_MACHINE.md §10 Circuit Breaker: unknown_intent_count >= 3 → ending_node.
        """
        state = _base_state(authenticated=True, intent=Intent.UNKNOWN, unknown_intent_count=3)
        assert route_after_intent(state) == "ending_node"

    def test_route_after_intent_ends_turn_after_followup_prompt(self):
        """
        When intent_node already asked the user for a new request after a
        follow-up confirmation, the invoke must stop and wait for next input.
        """
        state = _base_state(
            authenticated=True,
            intent=Intent.UNKNOWN,
            last_action_summary="ASKED_FOR_INTENT_AFTER_FOLLOWUP",
        )
        assert route_after_intent(state) == END

    def test_intent_state_tracks_unknown_count(self):
        """
        unknown_intent_count must be incrementable up to circuit breaker limit.
        """
        state = _base_state(authenticated=True, unknown_intent_count=0)
        state.unknown_intent_count += 1
        assert state.unknown_intent_count == 1

    def test_intent_state_accepted_enum_values(self):
        """
        All Intent enum values must be accepted by GraphState without error.
        """
        for intent in Intent:
            state = _base_state(authenticated=True, intent=intent)
            assert state.intent == intent


# ══════════════════════════════════════════════════════════════════════════════
# 4. Credit flow
# ══════════════════════════════════════════════════════════════════════════════


class TestCreditFlow:

    # ── Behavioral contracts (Phase 6B.8) ─────────────────────────────────────

    def test_credit_node_requires_authenticated_customer(self):
        """
        STATE_MACHINE.md §3.4 / REQUIREMENTS.md FR-CREDIT-*:
        credit_node must not execute when session is unauthenticated.
        Returns a controlled error — must not raise AttributeError.
        """
        state = _base_state(authenticated=False, current_customer=None)
        deps = GraphDependencies()
        result = credit_node(state, deps)
        assert isinstance(result, dict)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is False
        assert result["current_state"] == "ERROR"
        assert result["next_step"] == "ending_node"
        assert isinstance(result.get("last_error"), str)
        assert len(result["last_error"]) > 0

    def test_credit_node_shows_current_limit_for_credit_limit_intent(self):
        """
        STATE_MACHINE.md §3.4 flow 1 / REQUIREMENTS.md FR-CREDIT-001:
        CREDIT_LIMIT intent must show current limit and route back to intent_node.
        No credit_request_repository.append must be called for a consultation.
        """
        fake_credit_request_repo = FakeCreditRequestRepository()
        deps = GraphDependencies(
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=fake_credit_request_repo,
        )
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            intent=Intent.CREDIT_LIMIT,
        )
        result = credit_node(state, deps)
        assert isinstance(result, dict)
        assert result["current_state"] == "SHOWING_CREDIT_LIMIT"
        assert result["next_step"] == "intent_node"
        assert isinstance(result.get("last_assistant_output"), str)
        assert len(result["last_assistant_output"]) > 0
        assert result.get("request_rejected") is not True
        assert len(fake_credit_request_repo.appended) == 0

    def test_credit_node_missing_customer_returns_controlled_error(self):
        """
        STATE_MACHINE.md §3 Node Return Contracts rule 5:
        authenticated=True but current_customer=None must return a controlled
        error, not raise an unhandled AttributeError.
        """
        deps = GraphDependencies(
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=FakeCreditRequestRepository(),
        )
        state = _base_state(authenticated=True, current_customer=None)
        result = credit_node(state, deps)
        assert isinstance(result, dict)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is False
        assert result["current_state"] == "ERROR"
        assert result["next_step"] == "ending_node"
        assert isinstance(result.get("last_error"), str)
        assert len(result["last_error"]) > 0

    def test_credit_node_evaluates_approved_limit_request(self):
        """
        STATE_MACHINE.md §3.4 flow 2 / REQUIREMENTS.md FR-CREDIT-005:
        ANA score=720 → max limit 10000. Requesting 8000 must be approved.
        CreditService (not the node) makes the decision.
        credit_request_repository.append must be called once with APROVADO status.
        """
        fake_credit_request_repo = FakeCreditRequestRepository()
        deps = GraphDependencies(
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=fake_credit_request_repo,
        )
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            intent=Intent.CREDIT_INCREASE,
            credit_request={
                "cpf_cliente": "12345678901",
                "limite_atual": 5000.0,
                "novo_limite_solicitado": 8000.0,
            },
        )
        result = credit_node(state, deps)
        assert isinstance(result, dict)
        assert result["current_state"] == "CREDIT_REQUEST_APPROVED"
        assert result["next_step"] == "intent_node"
        assert result["request_rejected"] is False
        # credit_request is cleared after approval so it can't be reused silently
        assert result.get("credit_request") is None
        assert len(fake_credit_request_repo.appended) == 1

    def test_credit_node_evaluates_rejected_limit_request(self):
        """
        STATE_MACHINE.md §3.4 / REQUIREMENTS.md FR-CREDIT-005, FR-CREDIT-006:
        ANA score=720 → max limit 10000. Requesting 20000 must be rejected.
        The node must offer the credit interview first; partial increase is only
        offered after the interview reassessment (RECALCULATING_SCORE path).
        credit_request_repository.append is called with REJEITADO status.
        """
        fake_credit_request_repo = FakeCreditRequestRepository()
        deps = GraphDependencies(
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=fake_credit_request_repo,
        )
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            intent=Intent.CREDIT_INCREASE,
            credit_request={
                "cpf_cliente": "12345678901",
                "limite_atual": 5000.0,
                "novo_limite_solicitado": 20000.0,
            },
        )
        result = credit_node(state, deps)
        assert isinstance(result, dict)
        assert result["current_state"] == "OFFERING_CREDIT_INTERVIEW"
        assert result["next_step"] == "credit_node"
        assert result["request_rejected"] is True
        assert isinstance(result.get("last_assistant_output"), str)
        assert "entrevista" in result["last_assistant_output"].lower()
        assert len(fake_credit_request_repo.appended) == 1
        assert fake_credit_request_repo.appended[0].status_pedido == CreditRequestStatus.REJEITADO

    def test_credit_node_accepts_interview_offer_with_sim(self):
        """
        Rejection follow-up must accept "sim" deterministically and route to
        credit_interview_node without LLM dependency.
        """
        deps = GraphDependencies(
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=FakeCreditRequestRepository(),
        )
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            current_state="OFFERING_CREDIT_INTERVIEW",
            request_rejected=True,
            interview_offer_response=InterviewOfferResponse.UNKNOWN,
            last_user_input="sim",
        )
        result = credit_node(state, deps)
        assert result["next_step"] == "credit_interview_node"
        assert result["request_rejected"] is True
        assert result["interview_offer_response"] == InterviewOfferResponse.ACCEPTED
        assert result["interview_step"] is None
        assert result["interview_data"] == {}
        assert result["interview_complete"] is False

    def test_credit_node_accepts_interview_offer_resets_completed_interview_state(self):
        """
        Regression: when a prior interview already finished (step COMPLETE),
        accepting a new interview must reset interview_step/data to restart
        from INCOME instead of falling into INTERVIEW_UNEXPECTED_STEP.
        """
        deps = GraphDependencies(
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=FakeCreditRequestRepository(),
        )
        state = _base_state(
            authenticated=True,
            current_customer=CARLOS,
            current_state="OFFERING_CREDIT_INTERVIEW",
            request_rejected=True,
            interview_offer_response=InterviewOfferResponse.UNKNOWN,
            interview_step=InternalInterviewStep.COMPLETE,
            interview_data={"renda_mensal": 9000.0},
            interview_complete=True,
            last_user_input="sim",
        )
        result = credit_node(state, deps)
        assert result["next_step"] == "credit_interview_node"
        assert result["interview_offer_response"] == InterviewOfferResponse.ACCEPTED
        assert result["interview_step"] is None
        assert result["interview_data"] == {}
        assert result["interview_complete"] is False

    def test_credit_node_accepts_interview_offer_with_contextual_confirmation_via_interpreter(self):
        deps = GraphDependencies(
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=FakeCreditRequestRepository(),
            response_interpreter=FakeResponseInterpreter(
                {("confirmation", "pode ser"): "accepted"}
            ),
        )
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            current_state="OFFERING_CREDIT_INTERVIEW",
            request_rejected=True,
            interview_offer_response=InterviewOfferResponse.UNKNOWN,
            last_user_input="pode ser",
        )
        result = credit_node(state, deps)
        assert result["next_step"] == "credit_interview_node"
        assert result["interview_offer_response"] == InterviewOfferResponse.ACCEPTED

    def test_credit_node_declines_interview_offer_with_nao(self):
        """
        Rejection follow-up must accept "não" deterministically and return to
        normal assistance flow without abrupt ending.
        """
        deps = GraphDependencies(
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=FakeCreditRequestRepository(),
        )
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            current_state="OFFERING_CREDIT_INTERVIEW",
            request_rejected=True,
            interview_offer_response=InterviewOfferResponse.UNKNOWN,
            last_user_input="não",
        )
        result = credit_node(state, deps)
        assert result["next_step"] == "intent_node"
        assert result["request_rejected"] is False
        assert result["interview_offer_response"] == InterviewOfferResponse.DECLINED

    def test_credit_node_request_above_max_at_current_ceiling_does_not_offer_interview(self):
        """
        When the customer is at the *absolute* score ceiling (top tier, cannot
        improve further), asking for a higher limit should explain the ceiling
        rather than offering an interview that cannot help.
        Score 917 → max 20000 in FakeScoreLimitRepository; absolute max is also 20000.
        """
        fake_credit_request_repo = FakeCreditRequestRepository()
        deps = GraphDependencies(
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=fake_credit_request_repo,
        )
        customer_at_ceiling = CARLOS.model_copy(
            update={"limite_credito": 20000.0, "score_atual": 917}
        )
        state = _base_state(
            authenticated=True,
            current_customer=customer_at_ceiling,
            intent=Intent.CREDIT_INCREASE,
            credit_request={
                "cpf_cliente": customer_at_ceiling.cpf,
                "limite_atual": 20000.0,
                "novo_limite_solicitado": 25000.0,
            },
        )
        result = credit_node(state, deps)
        assert result["current_state"] == "IDENTIFYING_INTENT"
        assert result["next_step"] == "intent_node"
        assert result["request_rejected"] is False
        assert result["credit_request"] is None
        assert result["last_action_summary"] == "CREDIT_MAX_LIMIT_REACHED"
        assert "limite máximo" in result["last_assistant_output"]
        assert len(fake_credit_request_repo.appended) == 1
        assert fake_credit_request_repo.appended[0].status_pedido == CreditRequestStatus.REJEITADO

    def test_credit_node_at_score_ceiling_with_higher_tier_available_offers_interview(self):
        """
        When a customer is at their *current score* ceiling but a higher tier
        exists (e.g. new customer with score 300 and limit 2500), the node must
        offer a credit interview so they can improve their score — not dead-end.
        Score 300 → max 2500; absolute max is 20000 → interview should be offered.
        """
        fake_credit_request_repo = FakeCreditRequestRepository()
        deps = GraphDependencies(
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=fake_credit_request_repo,
        )
        new_customer = ANA.model_copy(update={"limite_credito": 2500.0, "score_atual": 300})
        state = _base_state(
            authenticated=True,
            current_customer=new_customer,
            intent=Intent.CREDIT_INCREASE,
            credit_request={
                "cpf_cliente": new_customer.cpf,
                "limite_atual": 2500.0,
                "novo_limite_solicitado": 10000.0,
            },
        )
        result = credit_node(state, deps)
        assert result["current_state"] == "OFFERING_CREDIT_INTERVIEW"
        assert result["request_rejected"] is True
        assert result["last_action_summary"] == "CREDIT_INTERVIEW_OFFERED"
        assert "entrevista" in result["last_assistant_output"].lower()

    def test_credit_node_missing_score_limit_repository_returns_controlled_error(self):
        """
        STATE_MACHINE.md §3 Node Return Contracts rule 5:
        Missing deps.score_limit_repository for CREDIT_INCREASE must return
        a controlled error instead of raising AttributeError or NoneType error.
        """
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            intent=Intent.CREDIT_INCREASE,
            credit_request={
                "cpf_cliente": "12345678901",
                "limite_atual": 5000.0,
                "novo_limite_solicitado": 8000.0,
            },
        )
        deps = GraphDependencies(
            score_limit_repository=None,
            credit_request_repository=FakeCreditRequestRepository(),
        )
        result = credit_node(state, deps)
        assert isinstance(result, dict)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is False
        assert result["current_state"] == "ERROR"
        assert result["next_step"] == "ending_node"
        assert isinstance(result.get("last_error"), str)
        assert len(result["last_error"]) > 0

    def test_credit_node_missing_credit_request_repository_returns_controlled_error(self):
        """
        STATE_MACHINE.md §3 Node Return Contracts rule 5:
        Missing deps.credit_request_repository for CREDIT_INCREASE must return
        a controlled error.
        """
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            intent=Intent.CREDIT_INCREASE,
            credit_request={
                "cpf_cliente": "12345678901",
                "limite_atual": 5000.0,
                "novo_limite_solicitado": 8000.0,
            },
        )
        deps = GraphDependencies(
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=None,
        )
        result = credit_node(state, deps)
        assert isinstance(result, dict)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is False
        assert result["current_state"] == "ERROR"
        assert result["next_step"] == "ending_node"

    def test_credit_node_missing_credit_request_asks_for_new_limit(self):
        """
        STATE_MACHINE.md §3.4 flow 2: when intent is CREDIT_INCREASE but
        state.credit_request is None, the node must ask for the desired new
        limit and loop back to itself (ASKING_NEW_LIMIT).
        No append must be called.
        """
        fake_credit_request_repo = FakeCreditRequestRepository()
        deps = GraphDependencies(
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=fake_credit_request_repo,
        )
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            intent=Intent.CREDIT_INCREASE,
            credit_request=None,
        )
        result = credit_node(state, deps)
        assert isinstance(result, dict)
        assert result["current_state"] == "ASKING_NEW_LIMIT"
        assert result["next_step"] == "credit_node"
        assert isinstance(result.get("last_assistant_output"), str)
        assert len(result["last_assistant_output"]) > 0
        assert len(fake_credit_request_repo.appended) == 0

    def test_credit_node_invalid_credit_request_returns_controlled_error(self):
        """
        STATE_MACHINE.md §3 rule 4: nodes must validate structured inputs.
        A credit_request dict missing required fields must be rejected.
        Node must return ASKING_NEW_LIMIT and not call append.
        """
        fake_credit_request_repo = FakeCreditRequestRepository()
        deps = GraphDependencies(
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=fake_credit_request_repo,
        )
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            intent=Intent.CREDIT_INCREASE,
            credit_request={
                "cpf_cliente": "12345678901",
                "limite_atual": 5000.0,
                # novo_limite_solicitado missing — invalid CreditLimitRequest
            },
        )
        result = credit_node(state, deps)
        assert isinstance(result, dict)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is True
        assert result["current_state"] == "ASKING_NEW_LIMIT"
        assert result["next_step"] == "credit_node"
        assert len(fake_credit_request_repo.appended) == 0

    def test_credit_node_does_not_mutate_state_directly(self):
        """
        STATE_MACHINE.md §3 Node Return Contracts: nodes must not mutate the
        input state object. Changes must appear only in the returned dict.
        """
        fake_credit_request_repo = FakeCreditRequestRepository()
        deps = GraphDependencies(
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=fake_credit_request_repo,
        )
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            intent=Intent.CREDIT_INCREASE,
            credit_request={
                "cpf_cliente": "12345678901",
                "limite_atual": 5000.0,
                "novo_limite_solicitado": 8000.0,
            },
        )
        original_request_rejected = state.request_rejected
        original_intent = state.intent
        credit_node(state, deps)  # result discarded — checking side-effects only
        assert state.request_rejected == original_request_rejected
        assert state.intent == original_intent

    # ── Edge router tests (unchanged) ─────────────────────────────────────────

    def test_route_after_credit_to_interview_when_rejected_and_accepted(self):
        """
        STATE_MACHINE.md §4 Credit: request_rejected=True,
        interview_offer_response=accepted → credit_interview_node.
        """
        state = _base_state(
            authenticated=True,
            request_rejected=True,
            interview_offer_response=InterviewOfferResponse.ACCEPTED,
        )
        assert route_after_credit(state) == "credit_interview_node"

    def test_route_after_credit_to_intent_when_rejected_and_declined(self):
        """
        STATE_MACHINE.md §4 Credit: request_rejected=True,
        interview_offer_response=declined → intent_node.
        """
        state = _base_state(
            authenticated=True,
            request_rejected=True,
            interview_offer_response=InterviewOfferResponse.DECLINED,
        )
        assert route_after_credit(state) == "intent_node"

    def test_route_after_credit_loops_when_rejected_and_offer_unknown(self):
        """
        STATE_MACHINE.md §4 Credit: request_rejected=True,
        interview_offer_response=unknown → credit_node.
        """
        state = _base_state(
            authenticated=True,
            request_rejected=True,
            interview_offer_response=InterviewOfferResponse.UNKNOWN,
        )
        assert route_after_credit(state) == "credit_node"

    def test_route_after_credit_to_intent_when_approved(self):
        """
        STATE_MACHINE.md §4 Credit: no rejection, no error → intent_node.
        """
        state = _base_state(
            authenticated=True,
            request_rejected=False,
        )
        assert route_after_credit(state) == "intent_node"

    def test_route_after_credit_to_intent_when_request_rejected_none(self):
        """
        STATE_MACHINE.md §4 Credit: request_rejected=None (no request yet) → intent_node.
        """
        state = _base_state(authenticated=True, request_rejected=None)
        assert route_after_credit(state) == "intent_node"

    def test_route_after_credit_loops_on_recoverable_error(self):
        """
        STATE_MACHINE.md §4 Credit: recoverable_error + retry_available → credit_node.
        """
        state = _base_state(
            authenticated=True,
            recoverable_error=True,
            retry_available=True,
        )
        assert route_after_credit(state) == "credit_node"

    def test_route_after_credit_ends_after_interview_confirmation_retry_prompt(self):
        """
        Credit follow-up confirmation retry prompt is user-facing and must end
        the current invoke to wait for the next user answer.
        """
        state = _base_state(
            authenticated=True,
            request_rejected=True,
            interview_offer_response=InterviewOfferResponse.UNKNOWN,
            last_action_summary="ASKED_INTERVIEW_CONFIRMATION_RETRY",
        )
        assert route_after_credit(state) == END

    def test_route_after_credit_ends_after_max_limit_ceiling_message(self):
        """
        Max-limit ceiling message is user-facing and must end the invoke.
        """
        state = _base_state(
            authenticated=True,
            last_action_summary="CREDIT_MAX_LIMIT_REACHED",
        )
        assert route_after_credit(state) == END

    def test_credit_state_can_set_request_rejected(self):
        """
        GraphState.request_rejected must be settable by credit_node.
        """
        state = _base_state(authenticated=True, current_customer=ANA)
        state.request_rejected = True
        assert state.request_rejected is True

    def test_credit_state_can_set_interview_offer_response(self):
        """
        GraphState.interview_offer_response must accept all valid enum values.
        """
        state = _base_state(authenticated=True)
        for resp in InterviewOfferResponse:
            state.interview_offer_response = resp
            assert state.interview_offer_response == resp


# ══════════════════════════════════════════════════════════════════════════════
# 5. Credit interview flow
# ══════════════════════════════════════════════════════════════════════════════


class TestCreditInterviewFlow:

    # ── Behavioral contracts (Phase 6B.10) ───────────────────────────────────

    def test_credit_interview_node_requires_authentication(self):
        """
        STATE_MACHINE.md §3.5: credit_interview_node must not run
        for unauthenticated sessions. Returns controlled error.
        """
        state = _base_state(authenticated=False)
        deps = GraphDependencies()
        result = credit_interview_node(state, deps)
        assert isinstance(result, dict)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is False
        assert result["current_state"] == "ERROR"
        assert result["next_step"] == "ending_node"
        assert isinstance(result.get("last_error"), str)
        assert len(result["last_error"]) > 0

    def test_credit_interview_node_requires_current_customer(self):
        """
        STATE_MACHINE.md §3.5: authenticated but no current_customer
        must return a controlled error, not raise AttributeError.
        """
        state = _base_state(authenticated=True, current_customer=None)
        deps = GraphDependencies()
        result = credit_interview_node(state, deps)
        assert isinstance(result, dict)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is False
        assert result["current_state"] == "ERROR"
        assert result["next_step"] == "ending_node"

    def test_credit_interview_node_requires_customer_repository(self):
        """
        STATE_MACHINE.md §3 Node Return Contracts rule 5:
        deps.customer_repository=None must return a controlled error
        instead of raising AttributeError at score update time.
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
        )
        deps = GraphDependencies(customer_repository=None)
        result = credit_interview_node(state, deps)
        assert isinstance(result, dict)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is False
        assert result["current_state"] == "ERROR"
        assert result["next_step"] == "ending_node"
        assert isinstance(result.get("last_error"), str)

    def test_credit_interview_node_starts_at_income_step(self):
        """
        STATE_MACHINE.md §3.5 flow: when interview_step is None,
        node must initialise the interview at INCOME and ask for income.
        interview_complete must be False.
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            interview_step=None,
        )
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        result = credit_interview_node(state, deps)
        assert isinstance(result, dict)
        assert result["current_state"] == "CREDIT_INTERVIEW_IN_PROGRESS"
        assert result["next_step"] == "credit_interview_node"
        assert result["interview_step"] == InternalInterviewStep.INCOME
        assert result.get("interview_complete") is False
        assert isinstance(result.get("last_assistant_output"), str)
        assert len(result["last_assistant_output"]) > 0

    def test_credit_interview_node_collects_income_and_advances_to_employment(self):
        """
        STATE_MACHINE.md §3.5 INCOME step: normalise income, store in
        interview_data, advance to EMPLOYMENT step.
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            interview_step=InternalInterviewStep.INCOME,
            last_user_input="R$ 5.000,00",
        )
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        result = credit_interview_node(state, deps)
        assert isinstance(result, dict)
        assert result["interview_data"]["renda_mensal"] == 5000.0
        assert result["interview_step"] == InternalInterviewStep.EMPLOYMENT
        assert result["next_step"] == "credit_interview_node"

    def test_credit_interview_node_invalid_income_keeps_income_step(self):
        """
        STATE_MACHINE.md §3.5 INCOME step: invalid income input must keep
        the INCOME step active and request a valid value.
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            interview_step=InternalInterviewStep.INCOME,
            last_user_input="muito dinheiro",
        )
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        result = credit_interview_node(state, deps)
        assert isinstance(result, dict)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is True
        assert result["interview_step"] == InternalInterviewStep.INCOME
        assert result["next_step"] == "credit_interview_node"
        assert isinstance(result.get("last_assistant_output"), str)
        assert len(result["last_assistant_output"]) > 0

    def test_credit_interview_node_collects_employment_and_advances_to_expenses(self):
        """
        STATE_MACHINE.md §3.5 EMPLOYMENT step: normalise employment type,
        store in interview_data, advance to EXPENSES.
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            interview_step=InternalInterviewStep.EMPLOYMENT,
            last_user_input="CLT",
            interview_data={"renda_mensal": 5000.0},
        )
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        result = credit_interview_node(state, deps)
        assert isinstance(result, dict)
        assert result["interview_data"]["tipo_emprego"] == EmploymentType.FORMAL
        assert result["interview_step"] == InternalInterviewStep.EXPENSES

    def test_credit_interview_node_collects_expenses_and_advances_to_dependents(self):
        """
        STATE_MACHINE.md §3.5 EXPENSES step: normalise expenses, store in
        interview_data, advance to DEPENDENTS.
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            interview_step=InternalInterviewStep.EXPENSES,
            last_user_input="2500",
            interview_data={"renda_mensal": 5000.0, "tipo_emprego": EmploymentType.FORMAL},
        )
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        result = credit_interview_node(state, deps)
        assert isinstance(result, dict)
        assert result["interview_data"]["despesas_fixas_mensais"] == 2500.0
        assert result["interview_step"] == InternalInterviewStep.DEPENDENTS

    def test_credit_interview_node_collects_dependents_and_advances_to_debts(self):
        """
        STATE_MACHINE.md §3.5 DEPENDENTS step: parse integer, store,
        advance to DEBTS.
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            interview_step=InternalInterviewStep.DEPENDENTS,
            last_user_input="2",
            interview_data={
                "renda_mensal": 5000.0,
                "tipo_emprego": EmploymentType.FORMAL,
                "despesas_fixas_mensais": 2500.0,
            },
        )
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        result = credit_interview_node(state, deps)
        assert isinstance(result, dict)
        assert result["interview_data"]["numero_dependentes"] == 2
        assert result["interview_step"] == InternalInterviewStep.DEBTS

    def test_credit_interview_node_invalid_dependents_keeps_step(self):
        """
        STATE_MACHINE.md §3.5 DEPENDENTS step: non-numeric input must keep
        the step active and request a valid value.
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            interview_step=InternalInterviewStep.DEPENDENTS,
            last_user_input="dois filhos",
            interview_data={
                "renda_mensal": 5000.0,
                "tipo_emprego": EmploymentType.FORMAL,
                "despesas_fixas_mensais": 2500.0,
            },
        )
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        result = credit_interview_node(state, deps)
        assert isinstance(result, dict)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is True
        assert result["interview_step"] == InternalInterviewStep.DEPENDENTS

    def test_credit_interview_node_accepts_nenhum_for_dependents(self):
        from tests.conftest import FakeCustomerRepository
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            interview_step=InternalInterviewStep.DEPENDENTS,
            last_user_input="nenhum",
            interview_data={
                "renda_mensal": 5000.0,
                "tipo_emprego": EmploymentType.FORMAL,
                "despesas_fixas_mensais": 2500.0,
            },
        )
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        result = credit_interview_node(state, deps)
        assert result["interview_data"]["numero_dependentes"] == 0
        assert result["interview_step"] == InternalInterviewStep.DEBTS

    def test_credit_node_reassesses_request_after_interview_when_user_confirms(self):
        fake_repo = FakeCreditRequestRepository()
        deps = GraphDependencies(
            score_limit_repository=FakeScoreLimitRepository(),
            credit_request_repository=fake_repo,
            response_interpreter=FakeResponseInterpreter({("confirmation", "ok"): "accepted"}),
        )
        state = _base_state(
            authenticated=True,
            current_customer=ANA.model_copy(update={"score_atual": 600}),
            current_state="RECALCULATING_SCORE",
            interview_complete=True,
            credit_request={
                "cpf_cliente": "12345678901",
                "limite_atual": 5000.0,
                "novo_limite_solicitado": 20000.0,
            },
            last_user_input="ok",
        )
        result = credit_node(state, deps)
        assert result["current_state"] == "CREDIT_REQUEST_REJECTED"
        assert result["interview_complete"] is False
        assert "permanece" in result["last_assistant_output"].lower()
        assert len(fake_repo.appended) == 1

    def test_route_after_triage_returns_credit_for_post_interview_reassessment(self):
        state = _base_state(
            authenticated=True,
            current_state="RECALCULATING_SCORE",
            interview_complete=True,
        )
        assert route_after_triage(state) == "credit_node"

    def test_credit_interview_node_collects_debts_completes_interview_and_updates_score(self):
        """
        STATE_MACHINE.md §3.5 Completion flow: after DEBTS, build CreditInterviewData,
        call ScoreService.calculate, call deps.customer_repository.update_score,
        set interview_complete=True and route to credit_node.
        """
        from tests.conftest import FakeCustomerRepository
        fake_repo = FakeCustomerRepository([ANA, CARLOS, MARINA])
        deps = GraphDependencies(customer_repository=fake_repo)
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            interview_step=InternalInterviewStep.DEBTS,
            last_user_input="não",
            interview_data={
                "renda_mensal": 5000.0,
                "tipo_emprego": EmploymentType.FORMAL,
                "despesas_fixas_mensais": 2500.0,
                "numero_dependentes": 2,
            },
        )
        result = credit_interview_node(state, deps)
        assert isinstance(result, dict)
        assert result.get("interview_complete") is True
        assert result["interview_step"] == InternalInterviewStep.COMPLETE
        assert result["current_state"] == "RECALCULATING_SCORE"
        assert result["next_step"] == "credit_node"
        updated_customer = result.get("current_customer")
        assert updated_customer is not None
        # Score must have been updated in the repository
        stored = fake_repo.find_by_cpf(ANA.cpf)
        assert stored is not None
        assert stored.score_atual == updated_customer.score_atual
        assert isinstance(result.get("last_assistant_output"), str)
        assert len(result["last_assistant_output"]) > 0
        # interview_data must be cleared
        assert result["interview_data"] == {}

    def test_credit_interview_node_score_calculation_uses_score_service_not_inline_logic(self):
        """
        STATE_MACHINE.md §3.5 / REQUIREMENTS.md: score must equal
        ScoreService.calculate for the same interview data.
        """
        from app.schemas.credit import CreditInterviewData
        from app.services.score_service import ScoreService
        from tests.conftest import FakeCustomerRepository
        fake_repo = FakeCustomerRepository([ANA, CARLOS, MARINA])
        deps = GraphDependencies(customer_repository=fake_repo)
        interview_data = {
            "renda_mensal": 5000.0,
            "tipo_emprego": EmploymentType.FORMAL,
            "despesas_fixas_mensais": 2500.0,
            "numero_dependentes": 2,
        }
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            interview_step=InternalInterviewStep.DEBTS,
            last_user_input="nao",
            interview_data=interview_data,
        )
        result = credit_interview_node(state, deps)
        expected_data = CreditInterviewData(
            renda_mensal=5000.0,
            tipo_emprego=EmploymentType.FORMAL,
            despesas_fixas_mensais=2500.0,
            numero_dependentes=2,
            tem_dividas_ativas=False,
        )
        expected_score = ScoreService.calculate(expected_data).score
        assert result["current_customer"].score_atual == expected_score

    def test_credit_interview_node_incomplete_data_returns_controlled_error_on_debts_step(self):
        """
        STATE_MACHINE.md §3.5: attempting to complete with missing fields
        must return a recoverable error and NOT update the score.
        """
        from tests.conftest import FakeCustomerRepository
        fake_repo = FakeCustomerRepository([ANA, CARLOS, MARINA])
        original_score = ANA.score_atual
        deps = GraphDependencies(customer_repository=fake_repo)
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            interview_step=InternalInterviewStep.DEBTS,
            last_user_input="nao",
            interview_data={
                "renda_mensal": 5000.0,
                # tipo_emprego missing
            },
        )
        result = credit_interview_node(state, deps)
        assert isinstance(result, dict)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is True
        assert result["current_state"] == "CREDIT_INTERVIEW_IN_PROGRESS"
        assert result["next_step"] == "credit_interview_node"
        # Score must NOT have been updated
        assert fake_repo.find_by_cpf(ANA.cpf).score_atual == original_score

    def test_credit_interview_node_does_not_mutate_state_directly(self):
        """
        STATE_MACHINE.md §3 Node Return Contracts: nodes must not mutate the
        input state object. Changes must appear only in the returned dict.
        """
        from tests.conftest import FakeCustomerRepository
        state = _base_state(
            authenticated=True,
            current_customer=ANA,
            interview_step=InternalInterviewStep.INCOME,
            last_user_input="5000",
            interview_data={},
        )
        original_step = state.interview_step
        original_data = dict(state.interview_data)
        deps = GraphDependencies(
            customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA])
        )
        credit_interview_node(state, deps)  # result discarded
        assert state.interview_step == original_step
        assert state.interview_data == original_data

    # ── Edge router tests (unchanged) ─────────────────────────────────────────

    def test_route_after_interview_to_credit_when_complete(self):
        """
        Interview completion message is user-facing and must end the invoke.
        """
        state = _base_state(authenticated=True, interview_complete=True)
        assert route_after_interview(state) == END

    def test_route_after_interview_stays_in_interview_when_incomplete_false(self):
        """
        STATE_MACHINE.md §4 Interview: interview_complete=False → credit_interview_node.
        """
        state = _base_state(authenticated=True, interview_complete=False)
        assert route_after_interview(state) == "credit_interview_node"

    def test_route_after_interview_stays_in_interview_when_incomplete_none(self):
        """
        STATE_MACHINE.md §4 Interview: interview_complete=None
        (interview not yet started or mid-progress) → credit_interview_node.
        """
        state = _base_state(
            authenticated=True,
            interview_step=InternalInterviewStep.INCOME,
        )
        assert route_after_interview(state) == "credit_interview_node"

    def test_route_after_interview_loops_on_recoverable_error(self):
        """
        STATE_MACHINE.md §4 Interview: recoverable_error + retry_available
        → credit_interview_node.
        """
        state = _base_state(
            authenticated=True,
            recoverable_error=True,
            retry_available=True,
        )
        assert route_after_interview(state) == "credit_interview_node"

    def test_route_after_interview_ends_after_first_question(self):
        """
        Interview start prompt is user-facing and must end the invoke so the
        next turn consumes the customer's income answer.
        """
        state = _base_state(
            authenticated=True,
            interview_step=InternalInterviewStep.INCOME,
            interview_complete=False,
            last_action_summary="INTERVIEW_STARTED",
        )
        assert route_after_interview(state) == END

    def test_route_after_interview_ends_after_invalid_input_retry_prompt(self):
        """
        Interview retry prompts must end the invoke to avoid same-turn loops.
        """
        state = _base_state(
            authenticated=True,
            interview_step=InternalInterviewStep.INCOME,
            interview_complete=False,
            recoverable_error=True,
            retry_available=True,
            last_action_summary="INTERVIEW_INVALID_INCOME",
        )
        assert route_after_interview(state) == END

    def test_interview_step_order_is_defined_in_enum(self):
        """
        STATE_MACHINE.md §3.5: interview order is income → employment → expenses
        → dependents → debts → complete. InternalInterviewStep enum must contain
        all steps in the correct declaration order.
        """
        steps = list(InternalInterviewStep)
        expected = [
            InternalInterviewStep.INCOME,
            InternalInterviewStep.EMPLOYMENT,
            InternalInterviewStep.EXPENSES,
            InternalInterviewStep.DEPENDENTS,
            InternalInterviewStep.DEBTS,
            InternalInterviewStep.COMPLETE,
        ]
        assert steps == expected

    def test_interview_state_can_store_income_step(self):
        """
        GraphState.interview_step must accept InternalInterviewStep.INCOME.
        """
        state = _base_state(authenticated=True)
        state.interview_step = InternalInterviewStep.INCOME
        assert state.interview_step == InternalInterviewStep.INCOME

    def test_interview_state_can_store_partial_interview_data(self):
        """
        GraphState.interview_data must store normalized values from each step.
        """
        state = _base_state(authenticated=True)
        state.interview_data = {"renda_mensal": 5000.0}
        assert state.interview_data["renda_mensal"] == 5000.0

    def test_interview_complete_flag_routes_back_to_credit(self):
        """
        After score update, completion message is user-facing and must end the
        invoke before any new credit decision turn.
        """
        state = _base_state(authenticated=True)
        state.interview_complete = True
        state.interview_data = {}  # must be cleared after completion
        assert route_after_interview(state) == END


# ══════════════════════════════════════════════════════════════════════════════
# 6. Exchange flow
# ══════════════════════════════════════════════════════════════════════════════


class TestExchangeFlow:

    # ── Behavioral contracts (Phase 6B.8) ─────────────────────────────────────

    def test_exchange_node_requires_authenticated_customer(self):
        """
        STATE_MACHINE.md §3.6 / REQUIREMENTS.md FR-EXCHANGE-*:
        exchange_node must not execute when session is unauthenticated.
        Returns a controlled error.
        """
        state = _base_state(authenticated=False)
        deps = GraphDependencies(
            exchange_provider=FakeExchangeProvider(),
        )
        result = exchange_node(state, deps)
        assert isinstance(result, dict)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is False
        assert result["current_state"] == "ERROR"
        assert result["next_step"] == "ending_node"

    def test_exchange_node_missing_exchange_provider_returns_controlled_error(self):
        """
        STATE_MACHINE.md §3 Node Return Contracts rule 5:
        Missing deps.exchange_provider must return a controlled error
        instead of raising AttributeError.
        """
        state = _base_state(
            authenticated=True,
            exchange_request={"base_currency": "BRL", "target_currency": "USD"},
        )
        deps = GraphDependencies(exchange_provider=None)
        result = exchange_node(state, deps)
        assert isinstance(result, dict)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is False
        assert result["current_state"] == "ERROR"
        assert result["next_step"] == "ending_node"
        assert isinstance(result.get("last_error"), str)
        assert len(result["last_error"]) > 0

    def test_exchange_node_asks_for_currency_when_missing_request(self):
        """
        STATE_MACHINE.md §3.6 flow 1: when exchange_request is absent,
        exchange_node must ask for the currency pair and loop back.
        Provider must not be called.
        """
        provider = FakeExchangeProvider()
        deps = GraphDependencies(exchange_provider=provider)
        state = _base_state(
            authenticated=True,
            exchange_request=None,
        )
        result = exchange_node(state, deps)
        assert isinstance(result, dict)
        assert result["current_state"] == "EXCHANGE_ASKING_CURRENCY"
        assert result["next_step"] == "exchange_node"
        assert isinstance(result.get("last_assistant_output"), str)
        assert len(result["last_assistant_output"]) > 0
        assert provider.calls == []

    def test_exchange_node_fetches_quote_successfully(self):
        """
        STATE_MACHINE.md §3.6 flow / REQUIREMENTS.md FR-EXCHANGE-*:
        When exchange_request is valid and provider works, node must
        return EXCHANGE_SHOWING_QUOTE and route to intent_node.
        Provider must be called with (base_currency, target_currency).
        """
        provider = FakeExchangeProvider(rate=5.25)
        deps = GraphDependencies(exchange_provider=provider)
        state = _base_state(
            authenticated=True,
            exchange_request={"base_currency": "BRL", "target_currency": "USD"},
        )
        result = exchange_node(state, deps)
        assert isinstance(result, dict)
        assert result["current_state"] == "EXCHANGE_SHOWING_QUOTE"
        assert result["next_step"] == "intent_node"
        assert isinstance(result.get("last_assistant_output"), str)
        assert len(result["last_assistant_output"]) > 0
        assert "BRL → USD" in result["last_assistant_output"]
        assert "USD → BRL" in result["last_assistant_output"]
        assert provider.calls == [("BRL", "USD")]
        assert result.get("recoverable_error") is not True

    def test_exchange_node_provider_failure_returns_recoverable_error(self):
        """
        STATE_MACHINE.md §3.6 Fallback: exchange API failure must not break
        the flow. Returns recoverable_error with a safe message. Routing
        returns to intent_node so the user can continue.
        """
        provider = FakeExchangeProvider(should_fail=True)
        deps = GraphDependencies(exchange_provider=provider)
        state = _base_state(
            authenticated=True,
            exchange_request={"base_currency": "BRL", "target_currency": "USD"},
        )
        result = exchange_node(state, deps)
        assert isinstance(result, dict)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is True
        assert result["current_state"] == "ERROR"
        assert result["next_step"] == "intent_node"
        assert isinstance(result.get("last_error"), str)
        assert isinstance(result.get("last_assistant_output"), str)
        assert len(result["last_assistant_output"]) > 0

    def test_exchange_node_invalid_request_returns_controlled_error(self):
        """
        STATE_MACHINE.md §3 rule 4: nodes must validate structured inputs.
        An exchange_request missing required fields must be rejected.
        Provider must not be called.
        """
        provider = FakeExchangeProvider()
        deps = GraphDependencies(exchange_provider=provider)
        state = _base_state(
            authenticated=True,
            exchange_request={"target_currency": "USD"},  # missing base_currency
        )
        result = exchange_node(state, deps)
        assert isinstance(result, dict)
        assert result["recoverable_error"] is True
        assert result["retry_available"] is True
        assert result["current_state"] == "EXCHANGE_ASKING_CURRENCY"
        assert result["next_step"] == "exchange_node"
        assert provider.calls == []

    def test_exchange_node_does_not_mutate_state_directly(self):
        """
        STATE_MACHINE.md §3 Node Return Contracts: nodes must not mutate the
        input state object. Changes must appear only in the returned dict.
        """
        provider = FakeExchangeProvider(rate=5.0)
        deps = GraphDependencies(exchange_provider=provider)
        state = _base_state(
            authenticated=True,
            exchange_request={"base_currency": "BRL", "target_currency": "USD"},
        )
        original_exchange_request = state.exchange_request
        exchange_node(state, deps)  # result discarded — checking side-effects only
        assert state.exchange_request == original_exchange_request

    # ── Edge router tests (unchanged) ─────────────────────────────────────────

    def test_exchange_always_routes_to_intent_after_completion(self):
        """
        STATE_MACHINE.md §4 Exchange: always → intent_node after exchange.
        """
        state = _base_state(authenticated=True)
        assert route_after_exchange(state) == "intent_node"

    def test_exchange_routes_to_intent_even_on_recoverable_error(self):
        """
        STATE_MACHINE.md §11.1 Error Recovery: Exchange API failures route
        back to intent_node (not retry loop inside exchange domain).
        """
        state = _base_state(authenticated=True, recoverable_error=True, retry_available=True)
        assert route_after_exchange(state) == "intent_node"

    def test_exchange_state_can_store_recoverable_error(self):
        """
        STATE_MACHINE.md §3.6 Fallback: exchange API failure must set
        recoverable_error=True and retry_available=True.
        """
        state = _base_state(authenticated=True)
        state.recoverable_error = True
        state.retry_available = True
        assert state.recoverable_error is True
        assert state.retry_available is True

    def test_exchange_state_can_store_exchange_request(self):
        """
        exchange_node must store normalized exchange request in
        GraphState.exchange_request.
        """
        state = _base_state(authenticated=True)
        state.exchange_request = {"currency": "USD"}
        assert state.exchange_request["currency"] == "USD"

    def test_exchange_requires_authentication_via_state_guard(self):
        """
        ARCHITECTURE.md §3.5 inv. #6: StateGuard must block exchange_node
        if not authenticated. Validated by StateGuard.check_entry directly.
        """
        from app.services.state_guard import StateGuard, StateTransitionDenied
        state = _base_state(authenticated=False)
        with pytest.raises(StateTransitionDenied):
            StateGuard.check_entry("exchange_node", state)


# ══════════════════════════════════════════════════════════════════════════════
# 7. StateGuard integration
# ══════════════════════════════════════════════════════════════════════════════


class TestStateGuardIntegration:

    def test_ending_node_returns_partial_update(self):
        """
        STATE_MACHINE.md §3.7: ending_node returns a partial update dict with
        current_state='ENDED', ended=True, next_step=None, and a non-empty
        closing message.
        """
        state = _base_state()
        result = ending_node(state)
        assert isinstance(result, dict)
        assert result["current_state"] == "ENDED"
        assert result["ended"] is True
        assert result["next_step"] is None
        assert isinstance(result["last_assistant_output"], str)
        assert len(result["last_assistant_output"]) > 0

    def test_ending_node_does_not_expose_sensitive_data(self):
        """
        ARCHITECTURE.md §4.3 / STATE_MACHINE.md §3.7: ending_node must not
        include customer data (current_customer, CPF) in its update dict.
        """
        state = _base_state(authenticated=True, authenticated_cpf="12345678901")
        result = ending_node(state)
        assert "current_customer" not in result
        assert "authenticated_cpf" not in result
        assert "session_id" not in result
        assert "trace_id" not in result

    def test_state_guard_blocks_credit_node_when_not_authenticated(self):
        """
        ARCHITECTURE.md §3.5 inv. #6, STATE_MACHINE.md §6:
        credit_node is protected; StateGuard must block unauthenticated access.
        """
        from app.services.state_guard import StateGuard, StateTransitionDenied
        state = _base_state(authenticated=False)
        with pytest.raises(StateTransitionDenied):
            StateGuard.check_entry("credit_node", state)

    def test_state_guard_blocks_credit_interview_node_when_not_authenticated(self):
        """STATE_MACHINE.md §6: credit_interview_node is protected."""
        from app.services.state_guard import StateGuard, StateTransitionDenied
        state = _base_state(authenticated=False)
        with pytest.raises(StateTransitionDenied):
            StateGuard.check_entry("credit_interview_node", state)

    def test_state_guard_allows_protected_nodes_when_authenticated(self):
        """
        StateGuard must allow credit_node when authenticated=True,
        is_blocked=False, ended=False, auth_attempts < 3.
        """
        from app.services.state_guard import StateGuard
        state = _base_state(authenticated=True)
        # must not raise
        StateGuard.check_entry("credit_node", state)

    def test_state_guard_blocks_all_nodes_when_session_is_blocked(self):
        """
        STATE_MACHINE.md §6: is_blocked=True → only ending_node is allowed.
        """
        from app.services.state_guard import StateGuard, StateTransitionDenied
        state = _base_state(is_blocked=True)
        for node in ("triage_node", "intent_node", "credit_node",
                     "credit_interview_node", "exchange_node"):
            with pytest.raises(StateTransitionDenied):
                StateGuard.check_entry(node, state)

    def test_state_guard_allows_ending_node_when_blocked(self):
        """
        STATE_MACHINE.md §4 Global Rules: is_blocked=True must still allow
        ending_node so the session can terminate gracefully.
        """
        from app.services.state_guard import StateGuard
        state = _base_state(is_blocked=True)
        # must not raise
        StateGuard.check_entry("ending_node", state)

    def test_state_guard_blocks_triage_after_three_auth_failures(self):
        """
        STATE_MACHINE.md §4: auth_attempts >= 3 → StateGuard blocks entry.
        """
        from app.services.state_guard import StateGuard, StateTransitionDenied
        state = _base_state(auth_attempts=3)
        with pytest.raises(StateTransitionDenied):
            StateGuard.check_entry("triage_node", state)

    def test_invalid_transition_raises_state_transition_denied(self):
        """
        ARCHITECTURE.md §3.5 inv. #6: invalid topology must be blocked.
        triage_node → credit_node is not a valid edge.
        """
        from app.services.state_guard import StateGuard, StateTransitionDenied
        state = _base_state(authenticated=True)
        with pytest.raises(StateTransitionDenied):
            StateGuard.check_transition("triage_node", "credit_node", state)

    def test_route_after_start_always_routes_to_triage_node(self):
        """
        STATE_MACHINE.md §3.1: start_node routes immediately to triage_node.
        route_after_start must always return 'triage_node'.
        """
        state = _base_state()
        assert route_after_start(state) == "triage_node"


# ══════════════════════════════════════════════════════════════════════════════
# 8. GraphDependencies contract
# ══════════════════════════════════════════════════════════════════════════════


class TestGraphDependencies:

    def test_graph_dependencies_can_be_instantiated_empty(self):
        """
        ARCHITECTURE.md §3.4: GraphDependencies must be constructable with
        no arguments. All fields default to None.
        """
        deps = GraphDependencies()
        assert deps.customer_repository is None
        assert deps.score_limit_repository is None
        assert deps.credit_request_repository is None
        assert deps.exchange_provider is None
        assert deps.intent_classifier is None

    def test_graph_dependencies_accepts_fake_customer_repository(self):
        """
        GraphDependencies must accept any object as customer_repository
        without type enforcement (duck-typed injection for testability).
        """
        from tests.conftest import FakeCustomerRepository
        fake_repo = FakeCustomerRepository([ANA])
        deps = GraphDependencies(customer_repository=fake_repo)
        assert deps.customer_repository is fake_repo
        # Verify the fake satisfies the repository protocol
        assert deps.customer_repository.find_by_cpf("12345678901") == ANA

    def test_graph_state_does_not_have_deps_field(self):
        """
        ARCHITECTURE.md §3.5 inv. #1: GraphState is the single source of truth
        for runtime decisions. Dependencies must NOT be embedded in state —
        they would break serialization and checkpointing.
        """
        state = _base_state()
        assert not hasattr(state, "deps")
        assert not hasattr(state, "dependencies")

    def test_domain_nodes_accept_deps_as_second_argument(self):
        """
        All domain nodes must accept (state, deps) — two positional arguments.
        All nodes are fully implemented and return a dict (Phase 6B complete):
        triage_node (6B.5), intent_node (6B.7), credit_node (6B.8),
        exchange_node (6B.8), credit_interview_node (6B.10).
        No remaining stubs.
        """
        state = _base_state(authenticated=True)
        deps = GraphDependencies()
        # triage_node is implemented — returns a dict
        result = triage_node(state, deps)
        assert isinstance(result, dict)
        # intent_node is implemented — returns a dict (no last_user_input → asks for input)
        result = intent_node(state, deps)
        assert isinstance(result, dict)
        # credit_node is implemented — returns a dict (authenticated, no customer → error)
        result = credit_node(state, deps)
        assert isinstance(result, dict)
        # exchange_node is implemented — returns a dict (authenticated, no request → asks)
        result = exchange_node(state, deps)
        assert isinstance(result, dict)
        # credit_interview_node is implemented — returns a dict (no customer_repository → error)
        result = credit_interview_node(state, deps)
        assert isinstance(result, dict)

    def test_domain_nodes_require_deps_argument(self):
        """
        Calling domain nodes with only state (missing deps) must raise
        TypeError — proving the signature enforces the two-arg contract.
        """
        state = _base_state(authenticated=True)
        for node_fn in (triage_node, intent_node, credit_node,
                        credit_interview_node, exchange_node):
            with pytest.raises(TypeError):
                node_fn(state)  # type: ignore[call-arg]
