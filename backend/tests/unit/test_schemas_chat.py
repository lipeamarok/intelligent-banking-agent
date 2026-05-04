"""
Unit tests for app/schemas/chat.py
"""

import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatMetadata, ChatRequest, ChatResponse
from app.schemas.common import PublicAgentLabel, PublicConversationState, SuggestedAction


# ── ChatRequest ───────────────────────────────────────────────────────────────


def test_chat_request_empty_message_fails():
    with pytest.raises(ValidationError):
        ChatRequest(message="")


def test_chat_request_whitespace_only_fails():
    with pytest.raises(ValidationError):
        ChatRequest(message="   ")


def test_chat_request_newline_only_fails():
    with pytest.raises(ValidationError):
        ChatRequest(message="\n\t  ")


def test_chat_request_valid_message_passes():
    req = ChatRequest(message="Quero consultar meu limite")
    assert req.message == "Quero consultar meu limite"


def test_chat_request_no_session_id_by_default():
    req = ChatRequest(message="Olá")
    assert req.session_id is None


def test_chat_request_with_session_id():
    req = ChatRequest(session_id="abc-123", message="Olá")
    assert req.session_id == "abc-123"


def test_chat_request_message_max_length_exceeded_fails():
    with pytest.raises(ValidationError):
        ChatRequest(message="x" * 2001)


def test_chat_request_message_at_max_length_passes():
    req = ChatRequest(message="x" * 2000)
    assert len(req.message) == 2000


# ── ChatResponse ──────────────────────────────────────────────────────────────


def test_chat_response_with_null_metadata_passes():
    resp = ChatResponse(
        session_id="session-001",
        reply="Olá, como posso ajudar?",
        agent=PublicAgentLabel.TRIAGE,
        state=PublicConversationState.STARTED,
        ended=False,
        trace_id="trace-001",
        metadata=None,
    )
    assert resp.metadata is None


def test_chat_response_with_metadata_passes():
    meta = ChatMetadata(
        recoverable=True,
        retry_available=False,
        suggested_action=SuggestedAction.CONTINUE,
    )
    resp = ChatResponse(
        session_id="session-001",
        reply="Informe seu CPF.",
        agent=PublicAgentLabel.TRIAGE,
        state=PublicConversationState.ASKING_CPF,
        ended=False,
        trace_id="trace-002",
        metadata=meta,
    )
    assert isinstance(resp.metadata, ChatMetadata)
    assert resp.metadata.recoverable is True


def test_chat_response_accepts_valid_agent_labels():
    for label in PublicAgentLabel:
        resp = ChatResponse(
            session_id="s",
            reply="ok",
            agent=label,
            state=PublicConversationState.STARTED,
            ended=False,
            trace_id="t",
        )
        assert resp.agent == label


def test_chat_response_accepts_valid_conversation_states():
    for state in PublicConversationState:
        resp = ChatResponse(
            session_id="s",
            reply="ok",
            agent=PublicAgentLabel.SYSTEM,
            state=state,
            ended=False,
            trace_id="t",
        )
        assert resp.state == state


def test_chat_metadata_default_suggested_action_is_none():
    meta = ChatMetadata(recoverable=True, retry_available=False)
    assert meta.suggested_action == SuggestedAction.NONE
