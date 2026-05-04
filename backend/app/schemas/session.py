"""
Public session API contracts.

This module contains only public-facing session schemas for the API.
The runtime conversational state is GraphState, defined in app/graph/state.py.
There is no SessionState implementation model in this codebase.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import PublicConversationState


class RecentMessage(BaseModel):
    """A single message turn stored in the session context window."""

    role: Literal["user", "assistant", "system"]
    content: str


class SessionResetRequest(BaseModel):
    """Request body for POST /api/v1/sessions/reset."""

    session_id: str | None = None


class SessionResetResponse(BaseModel):
    """Response body for POST /api/v1/sessions/reset."""

    message: str
    session_id: str
    state: PublicConversationState = PublicConversationState.STARTED
    ended: bool = False
    trace_id: str


class SessionResumeResponse(BaseModel):
    """Response body for GET /api/v1/sessions/resume/{session_id}."""

    session_id: str
    authenticated: bool
    state: PublicConversationState
    ended: bool
    recent_messages: list[RecentMessage] = Field(
        default_factory=list, max_length=3
    )
    trace_id: str
