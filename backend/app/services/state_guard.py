"""
StateGuard — Phase 4 implementation.

Enforces authentication, session state, and state machine transition rules.
Source of truth: STATE_MACHINE.md sections 5 and 6, REQUIREMENTS.md NFR-SEC-002.
"""

from app.graph.state import GraphState
from app.schemas.common import Intent


class StateTransitionDenied(Exception):
    """Raised when a requested state transition violates StateGuard rules."""


class StateGuard:
    """
    Enforces all state transition rules before any node executes.

    Rules enforced (STATE_MACHINE.md section 6):
    - Authentication is required before entering protected nodes.
    - Blocked sessions cannot enter any node.
    - Ended sessions cannot enter any node.
    - auth_attempts >= 3 results in session termination.
    - State transitions must follow the documented state machine.
    - Transitions suggested by LLM output are never accepted without
      passing through this guard.

    Protected nodes (require authenticated=True):
        credit_node, credit_interview_node, exchange_node
    """

    PROTECTED_NODES: frozenset[str] = frozenset(
        {"credit_node", "credit_interview_node", "exchange_node"}
    )

    @classmethod
    def check_entry(cls, target_node: str, state: GraphState) -> None:
        """
        Verify that the session is allowed to enter target_node.

        Raises:
            StateTransitionDenied: if session is blocked, ended, or unauthenticated
                                   for a protected node.
        """
        # ending_node is always reachable regardless of session state
        if target_node == "ending_node":
            return

        if state.is_blocked:
            raise StateTransitionDenied(
                f"Session is blocked; only ending_node is reachable, not {target_node!r}"
            )

        if state.ended:
            raise StateTransitionDenied(
                f"Session has ended; only ending_node is reachable, not {target_node!r}"
            )

        if state.auth_attempts >= 3:
            raise StateTransitionDenied(
                f"Max auth attempts reached; only ending_node is reachable, not {target_node!r}"
            )

        if target_node in cls.PROTECTED_NODES and not state.authenticated:
            raise StateTransitionDenied(
                f"{target_node!r} requires authentication"
            )

    @classmethod
    def check_transition(
        cls, from_node: str, to_node: str, state: GraphState
    ) -> None:
        """
        Verify that the transition from_node → to_node is valid per the state machine.

        Valid transitions are defined in STATE_MACHINE.md section 4.
        Invalid transitions must be rejected, logged, and redirected.

        Raises:
            StateTransitionDenied: if the transition is not allowed.
        """
        # ending_node is always reachable from any node
        if to_node == "ending_node":
            return

        # Defense-in-depth: protected nodes require authentication at the transition level too
        # (check_entry also enforces this; this is a second layer per ARCHITECTURE.md §3.5 inv. #6)
        if to_node in cls.PROTECTED_NODES and not state.authenticated:
            raise StateTransitionDenied(
                f"Transition to {to_node!r} requires authentication"
            )

        # triage_node → intent_node (requires authentication)
        if from_node == "triage_node" and to_node == "intent_node" and state.authenticated:
            return

        # intent_node → credit_node (credit_limit or credit_increase intent)
        if from_node == "intent_node" and to_node == "credit_node":
            if state.intent in {Intent.CREDIT_LIMIT, Intent.CREDIT_INCREASE}:
                return

        # intent_node → exchange_node (exchange_quote intent)
        if from_node == "intent_node" and to_node == "exchange_node":
            if state.intent == Intent.EXCHANGE_QUOTE:
                return

        raise StateTransitionDenied(
            f"Transition {from_node!r} → {to_node!r} is not a valid state machine edge"
        )
