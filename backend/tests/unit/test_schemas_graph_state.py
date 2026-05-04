"""
Unit tests for app/graph/state.py (GraphState) and app/schemas/session.py (public contracts).
"""

import pytest
from pydantic import ValidationError

from app.graph.state import GraphState
from app.schemas.common import PublicConversationState
from app.schemas.session import RecentMessage, SessionResetResponse, SessionResumeResponse


# ── GraphState defaults ───────────────────────────────────────────────────────


def test_graph_state_default_not_authenticated():
    state = GraphState(session_id="s1", trace_id="t1")
    assert state.authenticated is False


def test_graph_state_default_not_blocked():
    state = GraphState(session_id="s1", trace_id="t1")
    assert state.is_blocked is False


def test_graph_state_default_current_state_is_started():
    state = GraphState(session_id="s1", trace_id="t1")
    assert state.current_state == "STARTED"


def test_graph_state_default_not_ended():
    state = GraphState(session_id="s1", trace_id="t1")
    assert state.ended is False


def test_graph_state_default_fatal_error_is_false():
    state = GraphState(session_id="s1", trace_id="t1")
    assert state.fatal_error is False


def test_graph_state_default_recoverable_error_is_false():
    state = GraphState(session_id="s1", trace_id="t1")
    assert state.recoverable_error is False


def test_graph_state_default_retry_available_is_false():
    state = GraphState(session_id="s1", trace_id="t1")
    assert state.retry_available is False


def test_graph_state_default_interview_offer_response_is_none():
    state = GraphState(session_id="s1", trace_id="t1")
    assert state.interview_offer_response is None


def test_graph_state_default_recent_messages_is_empty():
    state = GraphState(session_id="s1", trace_id="t1")
    assert state.recent_messages == []


# ── GraphState recent_messages limit ─────────────────────────────────────────


def test_graph_state_recent_messages_max_3_enforced():
    msgs = [
        RecentMessage(role="user", content="1"),
        RecentMessage(role="assistant", content="2"),
        RecentMessage(role="user", content="3"),
        RecentMessage(role="assistant", content="4"),
    ]
    with pytest.raises(ValidationError):
        GraphState(session_id="s1", trace_id="t1", recent_messages=msgs)


def test_graph_state_recent_messages_exactly_3_passes():
    msgs = [
        RecentMessage(role="user", content="msg1"),
        RecentMessage(role="assistant", content="msg2"),
        RecentMessage(role="user", content="msg3"),
    ]
    state = GraphState(session_id="s1", trace_id="t1", recent_messages=msgs)
    assert len(state.recent_messages) == 3


# ── No SessionState ───────────────────────────────────────────────────────────


def test_no_session_state_in_session_module():
    import app.schemas.session as session_module

    assert not hasattr(session_module, "SessionState"), (
        "SessionState must not exist as an implementation model. "
        "Use GraphState for runtime state."
    )


def test_no_session_state_in_graph_state_module():
    import app.graph.state as state_module

    assert not hasattr(state_module, "SessionState"), (
        "SessionState alias must not exist in graph/state.py."
    )


# ── Session public contracts ──────────────────────────────────────────────────


def test_session_reset_response_defaults():
    resp = SessionResetResponse(
        message="Sessão reiniciada com sucesso.",
        session_id="new-session-uuid",
        trace_id="trace-001",
    )
    assert resp.state == PublicConversationState.STARTED
    assert resp.ended is False
    assert resp.session_id == "new-session-uuid"


def test_session_resume_response_max_3_messages_enforced():
    msgs = [
        RecentMessage(role="user", content="1"),
        RecentMessage(role="assistant", content="2"),
        RecentMessage(role="user", content="3"),
        RecentMessage(role="assistant", content="4"),
    ]
    with pytest.raises(ValidationError):
        SessionResumeResponse(
            session_id="s1",
            authenticated=True,
            state=PublicConversationState.AUTHENTICATED,
            ended=False,
            recent_messages=msgs,
            trace_id="trace-001",
        )


def test_session_resume_response_up_to_3_messages_passes():
    msgs = [
        RecentMessage(role="user", content="Quero crédito"),
        RecentMessage(role="assistant", content="Certo, informe seu CPF."),
    ]
    resp = SessionResumeResponse(
        session_id="s1",
        authenticated=False,
        state=PublicConversationState.ASKING_CPF,
        ended=False,
        recent_messages=msgs,
        trace_id="trace-001",
    )
    assert len(resp.recent_messages) == 2
