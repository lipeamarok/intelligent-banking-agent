"""
Phase 6C.1 — graph_builder behavioral contracts.

Tests validate that build_graph assembles a correct, executable LangGraph
compiled graph with in-memory checkpointing.

Source of truth: ARCHITECTURE.md §4.3, STATE_MACHINE.md sections 3–4,
DECISIONS.md ADR-001.

Rules verified:
- build_graph requires a GraphDependencies argument (TypeError on None).
- Returns a compiled graph with an .invoke() method.
- Uses in-memory checkpointer (thread_id via configurable).
- deps are NOT stored in GraphState output.
- session_id and trace_id are preserved through the graph.
- StateGuard protects credit_node, credit_interview_node, exchange_node.

Design note:
  All tests that call .invoke() use a "terminating state" — a pre-authenticated
  state + FakeIntentClassifier(END_CONVERSATION) — so the graph runs to END
  without looping. This isolates the graph_builder contract tests from
  multi-turn conversation complexity.
"""

import pytest

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


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_full_deps(
    classifier_result: Intent = Intent.END_CONVERSATION,
) -> GraphDependencies:
    """
    Build GraphDependencies with all fakes wired.
    Defaults classifier to END_CONVERSATION so invoke() naturally terminates.
    """
    return GraphDependencies(
        customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA]),
        score_limit_repository=FakeScoreLimitRepository(),
        credit_request_repository=FakeCreditRequestRepository(),
        exchange_provider=FakeExchangeProvider(),
        intent_classifier=FakeIntentClassifier(classifier_result),
    )


def _terminating_input(session_id: str = "s1", trace_id: str = "t1") -> dict:
    """
    GraphState input that terminates the graph in a single invoke() call.

    Sets authenticated=True + current_customer (bypasses triage auth via
    route_after_triage) and last_user_input="Encerrar" which the
    END_CONVERSATION classifier routes to ending_node.

    Flow: start → triage (ASKING_CPF, no auth override) →
          route_after_triage(authenticated=True) → intent_node(END_CONVERSATION)
          → ending_node → END
    """
    return {
        "session_id": session_id,
        "trace_id": trace_id,
        "authenticated": True,
        "current_customer": ANA.model_dump(),
        "last_user_input": "Encerrar atendimento",
    }


def _cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


# ── 1. build_graph requires deps ──────────────────────────────────────────────


class TestBuildGraphRequiresDependencies:

    def test_build_graph_with_none_raises_type_error(self):
        """
        ARCHITECTURE.md §4.3: build_graph must require GraphDependencies.
        build_graph(None) must raise TypeError or ValueError.
        """
        with pytest.raises((TypeError, ValueError)):
            build_graph(None)  # type: ignore[arg-type]

    def test_build_graph_with_valid_deps_does_not_raise(self):
        """
        build_graph with a valid GraphDependencies instance must not raise.
        """
        deps = _make_full_deps()
        graph = build_graph(deps)
        assert graph is not None


# ── 2. build_graph returns a compiled graph ───────────────────────────────────


class TestBuildGraphReturnsCompiledGraph:

    def test_returns_object_with_invoke_method(self):
        """
        ADR-001: LangGraph compiled graph must expose .invoke().
        """
        deps = _make_full_deps()
        graph = build_graph(deps)
        assert hasattr(graph, "invoke"), "Compiled graph must have .invoke()"
        assert callable(graph.invoke)

    def test_graph_is_invocable_with_initial_state(self):
        """
        Invoking build_graph(deps).invoke(state, config) must return a dict-like
        result without raising when the state is pre-authenticated.
        Flow: start → triage → intent(END_CONVERSATION) → ending_node → END.
        """
        deps = _make_full_deps()
        graph = build_graph(deps)
        result = graph.invoke(_terminating_input(), config=_cfg("build-test-001"))
        assert result is not None
        assert isinstance(result, dict)


# ── 3. In-memory checkpointer ─────────────────────────────────────────────────


class TestBuildGraphUsesMemoryCheckpointer:

    def test_invoke_with_thread_id_does_not_raise(self):
        """
        ADR-001: V1 checkpointer is MemorySaver.
        A graph compiled with a memory checkpointer must accept
        config={"configurable": {"thread_id": "..."}}.
        """
        deps = _make_full_deps()
        graph = build_graph(deps)
        result = graph.invoke(
            _terminating_input(), config=_cfg("checkpointer-test-001")
        )
        assert result is not None

    def test_multiple_invocations_with_different_thread_ids_are_independent(self):
        """
        Each thread_id must have its own independent checkpoint/state.
        Invoking the same compiled graph with two different thread_ids must
        produce independent sessions.
        """
        deps = _make_full_deps()
        graph = build_graph(deps)
        r1 = graph.invoke(
            _terminating_input("s-alpha", "t-alpha"),
            config=_cfg("thread-alpha"),
        )
        r2 = graph.invoke(
            _terminating_input("s-beta", "t-beta"),
            config=_cfg("thread-beta"),
        )
        # Both must succeed with their own session_ids intact
        assert r1.get("session_id") == "s-alpha"
        assert r2.get("session_id") == "s-beta"


# ── 4. thread_id requirement ──────────────────────────────────────────────────


class TestBuildGraphRequiresThreadId:

    def test_invoke_with_explicit_thread_id_succeeds(self):
        """
        STATE_MACHINE.md §2: sessions must be identifiable.
        config must include configurable.thread_id for the checkpointer.
        """
        deps = _make_full_deps()
        graph = build_graph(deps)
        result = graph.invoke(
            _terminating_input(), config=_cfg("explicit-thread-001")
        )
        assert result is not None


# ── 5. deps not stored in GraphState ─────────────────────────────────────────


class TestBuildGraphDoesNotStoreDepsInState:

    def test_result_does_not_contain_deps_key(self):
        """
        DECISIONS.md / ARCHITECTURE.md: GraphDependencies must NOT be stored
        in GraphState. Result dict must have no 'deps' or 'dependencies' key.
        """
        deps = _make_full_deps()
        graph = build_graph(deps)
        result = graph.invoke(_terminating_input(), config=_cfg("no-deps-test"))
        assert "deps" not in result
        assert "dependencies" not in result
        assert "intent_classifier" not in result

    def test_result_does_not_contain_repository_objects(self):
        """
        No repository object must leak into the serialised output state.
        """
        deps = _make_full_deps()
        graph = build_graph(deps)
        result = graph.invoke(
            _terminating_input(), config=_cfg("no-repo-test")
        )
        for key in (
            "customer_repository",
            "score_limit_repository",
            "credit_request_repository",
            "exchange_provider",
        ):
            assert key not in result, f"Key {key!r} must not leak into state"


# ── 6. Identity fields preserved ─────────────────────────────────────────────


class TestBuildGraphKeepsGraphStateIdentityFields:

    def test_session_id_preserved_after_invocation(self):
        """
        GraphState.session_id must be present in the returned state.
        LangGraph must not drop it through node transitions.
        """
        deps = _make_full_deps()
        graph = build_graph(deps)
        result = graph.invoke(
            _terminating_input(session_id="my-session-42", trace_id="my-trace-42"),
            config=_cfg("identity-test-001"),
        )
        assert result.get("session_id") == "my-session-42"

    def test_trace_id_preserved_after_invocation(self):
        """
        GraphState.trace_id must be present in the returned state.
        """
        deps = _make_full_deps()
        graph = build_graph(deps)
        result = graph.invoke(
            _terminating_input(session_id="sess-99", trace_id="trace-99"),
            config=_cfg("identity-test-002"),
        )
        assert result.get("trace_id") == "trace-99"


# ── 7. StateGuard protects sensitive nodes ────────────────────────────────────


class TestBuildGraphStateGuardProtectsNodes:

    def test_credit_node_denied_when_auth_revoked_mid_session(self):
        """
        ARCHITECTURE.md §3.5 / DECISIONS.md ADR-007:
        StateGuard must reject credit_node when authenticated=False,
        returning last_error='STATE_TRANSITION_DENIED'.

        Technique:
        1. interrupt_before=['intent_node'] pauses before intent_node.
        2. update_state(as_node='intent_node') advances past it as if
           intent_node had returned CREDIT_LIMIT with authenticated=False.
           route_after_intent(CREDIT_LIMIT) → credit_node.
        3. invoke(None): credit_node executes; _guarded_node detects
           authenticated=False → StateTransitionDenied → GUARD_DENIED dict.
        4. route_after_credit (recoverable=True, retry=False) → intent_node
           → interrupt fires again BEFORE intent_node can overwrite last_error.
        5. Returned state preserves last_error='STATE_TRANSITION_DENIED'.
        """
        deps = _make_full_deps(classifier_result=Intent.CREDIT_LIMIT)
        graph = build_graph(deps, interrupt_before=["intent_node"])

        # Turn 1: authenticated start → pause at intent_node
        graph.invoke(_terminating_input(), config=_cfg("guard-test-001"))

        # Simulate: intent_node returned CREDIT_LIMIT with auth revoked
        graph.update_state(
            _cfg("guard-test-001"),
            {"authenticated": False, "intent": Intent.CREDIT_LIMIT},
            as_node="intent_node",
        )

        # Turn 2: credit_node executes → guard denies → route_after_credit →
        #         intent_node → interrupted before it can overwrite last_error
        result = graph.invoke(None, config=_cfg("guard-test-001"))

        assert result.get("last_error") == "STATE_TRANSITION_DENIED"
        assert result.get("last_action_summary") == "STATE_GUARD_DENIED"
