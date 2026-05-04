"""
Unit tests for app/schemas/agent.py (AgentResponse).

Verifies that AgentResponse.state accepts only PublicConversationState values,
preventing internal LangGraph node names from leaking into the API contract.
"""

import pytest
from pydantic import ValidationError

from app.schemas.agent import AgentResponse
from app.schemas.common import PublicAgentLabel, PublicConversationState


def _base_kwargs(**overrides) -> dict:
    """Return minimal valid kwargs for AgentResponse."""
    defaults = dict(
        reply="Olá, como posso ajudar?",
        agent=PublicAgentLabel.TRIAGE,
        state=PublicConversationState.STARTED,
    )
    defaults.update(overrides)
    return defaults


# ── Casos válidos ─────────────────────────────────────────────────────────────


def test_agent_response_accepts_enum_value():
    resp = AgentResponse(**_base_kwargs(state=PublicConversationState.STARTED))
    assert resp.state == PublicConversationState.STARTED


def test_agent_response_accepts_string_coercion_for_valid_enum():
    """Pydantic v2 coerces "STARTED" (str, Enum) to PublicConversationState.STARTED."""
    resp = AgentResponse(**_base_kwargs(state="STARTED"))
    assert resp.state == PublicConversationState.STARTED


def test_agent_response_accepts_all_public_states():
    for state in PublicConversationState:
        resp = AgentResponse(**_base_kwargs(state=state))
        assert resp.state == state


def test_agent_response_defaults():
    resp = AgentResponse(**_base_kwargs())
    assert resp.state_update == {}
    assert resp.decision_rationale is None
    assert resp.recoverable_error is False
    assert resp.retry_available is False
    assert resp.fatal_error is False
    assert resp.metadata is None


# ── Casos inválidos — nomes internos de LangGraph nodes ──────────────────────


def test_agent_response_rejects_triage_node():
    with pytest.raises(ValidationError):
        AgentResponse(**_base_kwargs(state="triage_node"))


def test_agent_response_rejects_intent_node():
    with pytest.raises(ValidationError):
        AgentResponse(**_base_kwargs(state="intent_node"))


def test_agent_response_rejects_ending_node():
    with pytest.raises(ValidationError):
        AgentResponse(**_base_kwargs(state="ending_node"))


def test_agent_response_rejects_credit_node():
    with pytest.raises(ValidationError):
        AgentResponse(**_base_kwargs(state="credit_node"))


# ── Casos inválidos — estados internos de entrevista não expostos ─────────────


def test_agent_response_rejects_internal_interview_income():
    with pytest.raises(ValidationError):
        AgentResponse(**_base_kwargs(state="CREDIT_INTERVIEW_INCOME"))


def test_agent_response_rejects_internal_interview_employment():
    with pytest.raises(ValidationError):
        AgentResponse(**_base_kwargs(state="CREDIT_INTERVIEW_EMPLOYMENT"))


def test_agent_response_rejects_internal_interview_expenses():
    with pytest.raises(ValidationError):
        AgentResponse(**_base_kwargs(state="CREDIT_INTERVIEW_EXPENSES"))


def test_agent_response_rejects_internal_interview_dependents():
    with pytest.raises(ValidationError):
        AgentResponse(**_base_kwargs(state="CREDIT_INTERVIEW_DEPENDENTS"))


def test_agent_response_rejects_arbitrary_string():
    with pytest.raises(ValidationError):
        AgentResponse(**_base_kwargs(state="some_random_internal_name"))
