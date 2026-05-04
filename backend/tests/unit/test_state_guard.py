"""
Unit tests for StateGuard.

Source of truth: STATE_MACHINE.md sections 5 and 6, REQUIREMENTS.md NFR-SEC-002.
"""

import pytest

from app.services.state_guard import StateGuard, StateTransitionDenied
from tests.conftest import ANA, make_graph_state


# ── Authentication gate ────────────────────────────────────────────────────────


def test_state_guard_blocks_credit_node_if_not_authenticated():
    """REQUIREMENTS.md NFR-SEC-001: credit requires authentication."""
    state = make_graph_state(authenticated=False)
    with pytest.raises(StateTransitionDenied):
        StateGuard.check_entry("credit_node", state)


def test_state_guard_blocks_credit_interview_node_if_not_authenticated():
    """FR-INTERVIEW-001: interview requires authentication."""
    state = make_graph_state(authenticated=False)
    with pytest.raises(StateTransitionDenied):
        StateGuard.check_entry("credit_interview_node", state)


def test_state_guard_blocks_exchange_node_if_not_authenticated():
    """FR-EXCHANGE-001: exchange requires authentication."""
    state = make_graph_state(authenticated=False)
    with pytest.raises(StateTransitionDenied):
        StateGuard.check_entry("exchange_node", state)


def test_state_guard_allows_protected_node_when_authenticated_and_not_blocked():
    """Authenticated, unblocked session may enter protected nodes."""
    state = make_graph_state(
        authenticated=True,
        is_blocked=False,
        current_customer=ANA,
    )
    # Must not raise — StateGuard should pass
    StateGuard.check_entry("credit_node", state)


def test_state_guard_allows_triage_node_unauthenticated():
    """triage_node is always accessible."""
    state = make_graph_state(authenticated=False)
    StateGuard.check_entry("triage_node", state)


def test_state_guard_allows_intent_node_when_authenticated():
    """intent_node is accessible for authenticated sessions."""
    state = make_graph_state(authenticated=True)
    StateGuard.check_entry("intent_node", state)


# ── Blocked session gate ───────────────────────────────────────────────────────


def test_state_guard_blocks_any_node_if_session_is_blocked():
    """STATE_MACHINE.md global rule: is_blocked=True → ending_node only."""
    state = make_graph_state(authenticated=True, is_blocked=True)
    with pytest.raises(StateTransitionDenied):
        StateGuard.check_entry("credit_node", state)


def test_state_guard_blocks_triage_node_if_session_is_blocked():
    """Blocked sessions cannot re-enter triage."""
    state = make_graph_state(authenticated=False, is_blocked=True)
    with pytest.raises(StateTransitionDenied):
        StateGuard.check_entry("triage_node", state)


def test_state_guard_allows_ending_node_when_blocked():
    """ending_node must always be reachable, including when blocked."""
    state = make_graph_state(authenticated=True, is_blocked=True)
    StateGuard.check_entry("ending_node", state)


# ── Ended session gate ─────────────────────────────────────────────────────────


def test_state_guard_blocks_entry_when_session_ended():
    """STATE_MACHINE.md global rule: ended=True → only ending_node."""
    state = make_graph_state(authenticated=True, ended=True)
    with pytest.raises(StateTransitionDenied):
        StateGuard.check_entry("credit_node", state)


def test_state_guard_blocks_triage_when_ended():
    state = make_graph_state(ended=True)
    with pytest.raises(StateTransitionDenied):
        StateGuard.check_entry("triage_node", state)


# ── auth_attempts limit ────────────────────────────────────────────────────────


def test_state_guard_blocks_entry_after_three_auth_attempts():
    """
    STATE_MACHINE.md section 4 Triage: auth_attempts >= 3 → ending_node.
    StateGuard must enforce this even if is_blocked has not been set yet.
    """
    state = make_graph_state(authenticated=False, auth_attempts=3)
    with pytest.raises(StateTransitionDenied):
        StateGuard.check_entry("triage_node", state)


def test_state_guard_allows_entry_with_two_auth_attempts():
    """Two failed attempts — still within limit, triage should proceed."""
    state = make_graph_state(authenticated=False, auth_attempts=2)
    StateGuard.check_entry("triage_node", state)


# ── Valid state machine transitions ───────────────────────────────────────────


def test_state_guard_allows_triage_to_intent_when_authenticated():
    """STATE_MACHINE.md Triage section: authenticated=True → intent_node."""
    state = make_graph_state(authenticated=True)
    StateGuard.check_transition("triage_node", "intent_node", state)


def test_state_guard_allows_intent_to_credit_when_intent_is_credit():
    """STATE_MACHINE.md Intent section: intent=credit → credit_node."""
    from app.schemas.common import Intent
    state = make_graph_state(authenticated=True, intent=Intent.CREDIT_LIMIT)
    StateGuard.check_transition("intent_node", "credit_node", state)


def test_state_guard_allows_intent_to_exchange_when_intent_is_exchange():
    """STATE_MACHINE.md Intent section: intent=exchange → exchange_node."""
    from app.schemas.common import Intent
    state = make_graph_state(authenticated=True, intent=Intent.EXCHANGE_QUOTE)
    StateGuard.check_transition("intent_node", "exchange_node", state)


def test_state_guard_allows_any_node_to_ending():
    """Any node can transition to ending_node."""
    state = make_graph_state(authenticated=True)
    StateGuard.check_transition("credit_node", "ending_node", state)


# ── Invalid state machine transitions ─────────────────────────────────────────


def test_state_guard_rejects_triage_to_credit_directly():
    """
    STATE_MACHINE.md: triage_node cannot jump directly to credit_node.
    Must go through intent_node first.
    """
    state = make_graph_state(authenticated=True)
    with pytest.raises(StateTransitionDenied):
        StateGuard.check_transition("triage_node", "credit_node", state)


def test_state_guard_rejects_triage_to_exchange_directly():
    """triage_node → exchange_node is not a valid transition."""
    state = make_graph_state(authenticated=True)
    with pytest.raises(StateTransitionDenied):
        StateGuard.check_transition("triage_node", "exchange_node", state)


def test_state_guard_rejects_exchange_to_credit_directly():
    """exchange_node → credit_node is not a valid transition."""
    state = make_graph_state(authenticated=True)
    with pytest.raises(StateTransitionDenied):
        StateGuard.check_transition("exchange_node", "credit_node", state)


# ── LLM-suggested transition must not bypass StateGuard ───────────────────────


def test_state_guard_rejects_llm_suggested_invalid_transition():
    """
    ARCHITECTURE.md 3.2 / STATE_MACHINE.md section 5:
    Transitions suggested by LLM output are never accepted without
    validation by StateGuard. This test simulates a LLM suggesting
    a direct triage_node → credit_node jump for an unauthenticated session.
    StateGuard must reject it regardless of the source.
    """
    # Simulate LLM suggesting "go to credit" for unauthenticated session
    state = make_graph_state(authenticated=False)
    with pytest.raises(StateTransitionDenied):
        # This would be an LLM-suggested jump — StateGuard must block it
        StateGuard.check_entry("credit_node", state)


def test_state_guard_rejects_llm_suggested_invalid_node_to_node():
    """
    An authenticated session with LLM suggesting triage_node → credit_interview_node
    (skipping intent_node) must be rejected.
    """
    state = make_graph_state(authenticated=True)
    with pytest.raises(StateTransitionDenied):
        StateGuard.check_transition("triage_node", "credit_interview_node", state)


# ── check_transition: authentication guard for protected nodes ────────────────


def test_check_transition_blocks_intent_to_credit_when_not_authenticated():
    """
    ARCHITECTURE.md §3.5 inv. #6: state transitions always pass through StateGuard.
    STATE_MACHINE.md §6: StateGuard enforces authentication before protected flows.
    Even if topological edge is valid (intent → credit), unauthenticated session
    must be denied at the transition level as well.
    """
    from app.schemas.common import Intent
    state = make_graph_state(authenticated=False, intent=Intent.CREDIT_LIMIT)
    with pytest.raises(StateTransitionDenied):
        StateGuard.check_transition("intent_node", "credit_node", state)


def test_check_transition_blocks_intent_to_exchange_when_not_authenticated():
    """
    Defense-in-depth: exchange_node is a protected node.
    Unauthenticated session must be denied at both check_entry and check_transition.
    """
    from app.schemas.common import Intent
    state = make_graph_state(authenticated=False, intent=Intent.EXCHANGE_QUOTE)
    with pytest.raises(StateTransitionDenied):
        StateGuard.check_transition("intent_node", "exchange_node", state)
