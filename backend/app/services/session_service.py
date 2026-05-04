"""In-memory session management for V1 conversational API."""

import uuid
from typing import Any


class SessionService:
    """
    In-memory session storage for V1.

    Each session holds a minimal snapshot of conversational state.
    """

    def __init__(self):
        self._sessions: dict[str, dict[str, Any]] = {}

    def create_session(self) -> str:
        """Create a new session and return a UUID session_id."""
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            "recent_messages": [],
            "graph_state": {
                "session_id": session_id,
                "current_state": "STARTED",
                "authenticated": False,
                "ended": False,
            },
        }
        return session_id

    def reset_session(self, session_id: str | None = None) -> str:
        """Reset a session and always return a new clean session id."""
        if session_id and session_id in self._sessions:
            del self._sessions[session_id]
        return self.create_session()

    def get_state(self, session_id: str) -> dict[str, Any] | None:
        """Get stored state for a session id, or None."""
        return self._sessions.get(session_id)

    def save_state(self, session_id: str, state: dict[str, Any]) -> None:
        """Persist state snapshot for a session id."""
        self._sessions[session_id] = state

    def resume_session(self, session_id: str) -> dict[str, Any] | None:
        """Retrieve session snapshot for resume endpoint."""
        return self._sessions.get(session_id)

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        return session_id in self._sessions
