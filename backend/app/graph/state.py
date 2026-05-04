"""
GraphState — the single source of truth for runtime conversational state.

Source of truth: STATE_MACHINE.md section 2.
This is a Pydantic v2 model for schema validation and serialization.
LangGraph integration (TypedDict adaptation) happens in a future phase.

Rules:
- Must not store secrets, raw stack traces, or provider credentials.
- recent_messages is limited to a maximum of 3 turns.
- Raw user input may only appear in last_user_input and recent_messages.
- Domain stores (credit_request, interview_data, exchange_request) must
  contain only normalized, validated data.
- No LangGraph imports here.
- No SessionState alias or class in this module.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Intent, InternalInterviewStep, InterviewOfferResponse
from app.schemas.customer import Customer
from app.schemas.errors import ErrorCode
from app.schemas.session import RecentMessage


class GraphState(BaseModel):
    """
    Runtime conversational state propagated across the agent graph.

    Serializable, typed, and auditable. Must not grow unboundedly.
    """

    model_config = ConfigDict(validate_assignment=True)

    # ── Identity ──────────────────────────────────────────────────────────────
    session_id: str
    trace_id: str

    # ── Security ──────────────────────────────────────────────────────────────
    authenticated: bool = False
    auth_attempts: int = 0
    is_blocked: bool = False

    # ── Customer context ──────────────────────────────────────────────────────
    cpf_candidate: str | None = None
    birth_date_candidate: str | None = None
    authenticated_cpf: str | None = None
    current_customer: Customer | None = None

    # ── Flow control ──────────────────────────────────────────────────────────
    current_state: str = "STARTED"
    previous_state: str | None = None
    next_step: str | None = None
    ended: bool = False

    # ── Intent ────────────────────────────────────────────────────────────────
    intent: Intent | None = None
    unknown_intent_count: int = 0

    # ── Conversation memory ───────────────────────────────────────────────────
    # recent_messages: max 3 turns — must not grow unboundedly
    last_user_input: str | None = None
    last_assistant_output: str | None = None
    recent_messages: list[RecentMessage] = Field(
        default_factory=list, max_length=3
    )
    last_action_summary: str | None = None
    system_bridge_message: str | None = None

    # ── Domain stores (normalized data only, no raw user input) ───────────────
    credit_request: dict[str, Any] | None = None
    request_rejected: bool | None = None
    offered_partial_limit: float | None = None
    interview_offer_response: InterviewOfferResponse | None = None
    interview_data: dict[str, Any] = Field(default_factory=dict)
    interview_step: InternalInterviewStep | None = None
    interview_complete: bool | None = None
    exchange_request: dict[str, Any] | None = None
    registration_data: dict[str, Any] = Field(default_factory=dict)

    # ── Recovery ──────────────────────────────────────────────────────────────
    recoverable_error: bool = False
    retry_available: bool = False
    fatal_error: bool = False

    # ── Observability ─────────────────────────────────────────────────────────
    provider_used: str | None = None
    fallback_triggered: bool = False
    decision_rationale: str | None = None
    # last_error: known ErrorCode or short safe diagnostic string — no stack traces
    last_error: ErrorCode | str | None = None
