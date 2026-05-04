"""
Public chat API request/response contracts.

Source of truth: API_CONTRACT.md sections 8 and 5.
"""

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import PublicAgentLabel, PublicConversationState, SuggestedAction


class ChatMetadata(BaseModel):
    """Optional metadata attached to a chat response for client recovery guidance."""

    recoverable: bool
    retry_available: bool
    suggested_action: SuggestedAction = SuggestedAction.NONE
    last_action_summary: str | None = None
    adherence_flag: bool = False


class ChatRequest(BaseModel):
    """Request body for POST /api/v1/chat."""

    session_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be blank or whitespace-only")
        return v


class ChatResponse(BaseModel):
    """
    Response body for POST /api/v1/chat.

    Must not expose: GraphState internals, customer PII, LangGraph node names,
    raw LLM output, or internal service details.
    """

    session_id: str
    reply: str
    agent: PublicAgentLabel
    state: PublicConversationState
    ended: bool
    trace_id: str
    metadata: ChatMetadata | None = None
