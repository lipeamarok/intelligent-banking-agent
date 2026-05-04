"""
Internal agent response contract.

AgentResponse is the internal contract returned by each agent node to the orchestrator.
It must not be exposed directly to the frontend.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.chat import ChatMetadata
from app.schemas.common import PublicAgentLabel, PublicConversationState


class AgentResponse(BaseModel):
    """
    Internal response produced by an agent node.

    Rules:
    - Must not expose raw LLM output.
    - Must not expose LangGraph node names to the frontend.
    - Must not calculate scores or make business decisions.
    - Must not access CSV or call LLMs.
    - state must be PublicConversationState: agents are responsible for mapping
      internal graph states to the public enum before returning AgentResponse.
      This prevents internal LangGraph node names from leaking into ChatResponse.
    """

    reply: str
    agent: PublicAgentLabel
    state: PublicConversationState
    state_update: dict[str, Any] = Field(default_factory=dict)
    decision_rationale: str | None = None
    recoverable_error: bool = False
    retry_available: bool = False
    fatal_error: bool = False
    metadata: ChatMetadata | None = None
