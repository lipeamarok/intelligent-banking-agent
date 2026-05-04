"""Session endpoints for reset and resume operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_session_service, get_trace_id
from app.schemas.common import PublicConversationState, SuggestedAction
from app.schemas.errors import ErrorCode, ErrorDetail, ErrorResponse
from app.schemas.session import SessionResetRequest, SessionResetResponse, SessionResumeResponse
from app.services.session_service import SessionService

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def _to_public_state(raw_state: str | None) -> PublicConversationState:
    if not raw_state:
        return PublicConversationState.STARTED

    if raw_state.startswith("CREDIT_INTERVIEW_"):
        return PublicConversationState.CREDIT_INTERVIEW_IN_PROGRESS

    try:
        return PublicConversationState(raw_state)
    except ValueError:
        return PublicConversationState.ERROR


@router.post("/reset", response_model=SessionResetResponse)
def reset_session(
    request: SessionResetRequest | None = None,
    session_service: SessionService = Depends(get_session_service),
    trace_id: str = Depends(get_trace_id),
) -> SessionResetResponse:
    """Reset an existing session or create a new clean session."""
    new_session_id = session_service.reset_session(request.session_id if request else None)
    return SessionResetResponse(
        message="Session reset successfully",
        session_id=new_session_id,
        state=PublicConversationState.STARTED,
        ended=False,
        trace_id=trace_id,
    )


@router.get("/{session_id}", response_model=SessionResumeResponse)
@router.get("/resume/{session_id}", response_model=SessionResumeResponse)
def resume_session(
    session_id: str,
    session_service: SessionService = Depends(get_session_service),
    trace_id: str = Depends(get_trace_id),
) -> SessionResumeResponse:
    """Resume an existing session with safe public data only."""
    snapshot = session_service.resume_session(session_id)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.SESSION_NOT_FOUND,
                    message="Session not found",
                    trace_id=trace_id,
                    recoverable=False,
                    suggested_action=SuggestedAction.RESET,
                )
            ).model_dump(),
        )

    graph_state = snapshot.get("graph_state", {})
    recent_messages = snapshot.get("recent_messages", [])[-3:]

    return SessionResumeResponse(
        session_id=session_id,
        authenticated=bool(graph_state.get("authenticated", False)),
        state=_to_public_state(graph_state.get("current_state")),
        ended=bool(graph_state.get("ended", False)),
        recent_messages=recent_messages,
        trace_id=trace_id,
    )
