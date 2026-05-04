"""
LangGraph graph builder — Phase 6C implementation.

Assembles nodes, conditional edges, and StateGuard protection into a
compiled StateGraph with in-memory checkpointing (V1).

Source of truth: ARCHITECTURE.md §4.3, STATE_MACHINE.md sections 3–4,
DECISIONS.md ADR-001.

Rules:
- GraphDependencies is injected via closures. It must NOT enter GraphState.
- GraphState (Pydantic BaseModel) is used as the LangGraph state schema.
  LangGraph 1.x supports this directly; nodes receive typed GraphState instances.
- Nodes return partial dict updates; LangGraph merges them into state.
- StateGuard wraps protected nodes (credit_node, credit_interview_node,
  exchange_node) to deny unauthenticated or blocked sessions before node logic.
- MemorySaver provides in-memory checkpointing for V1 (ADR-001).
- No LLM calls, no CSV access, no API layer here.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.graph.dependencies import GraphDependencies
from app.graph.edges import (
    route_after_credit,
    route_after_exchange,
    route_after_intent,
    route_after_interview,
    route_after_registration,
    route_after_start,
    route_after_triage,
)
from app.graph.nodes import (
    credit_interview_node,
    credit_node,
    ending_node,
    exchange_node,
    intent_node,
    registration_node,
    start_node,
    triage_node,
)
from app.graph.state import GraphState
from app.services.state_guard import StateGuard, StateTransitionDenied

# ── StateGuard denial update ──────────────────────────────────────────────────
# Returned by protected-node wrappers when StateGuard.check_entry raises.

_GUARD_DENIED_UPDATE: dict[str, Any] = {
    "current_state": "ERROR",
    "next_step": "ending_node",
    "recoverable_error": True,
    "retry_available": False,
    "last_error": "STATE_TRANSITION_DENIED",
    "last_assistant_output": (
        "Não foi possível continuar o atendimento com segurança."
    ),
    "last_action_summary": "STATE_GUARD_DENIED",
}


def _guarded_node(node_fn, node_name: str, deps: GraphDependencies):
    """
    Return a node wrapper that runs StateGuard.check_entry before node logic.

    If the guard raises StateTransitionDenied, returns a controlled error
    dict instead of calling the underlying node. deps is captured by closure.
    """

    def _wrapped(state: GraphState) -> dict:
        try:
            StateGuard.check_entry(node_name, state)
        except StateTransitionDenied:
            return dict(_GUARD_DENIED_UPDATE)
        return node_fn(state, deps)

    return _wrapped


def build_graph(
    deps: GraphDependencies,
    checkpointer: Any = None,
    interrupt_before: list[str] | None = None,
) -> Any:
    """
    Build and compile the LangGraph StateGraph for Banco Ágil.

    Args:
        deps: Required. GraphDependencies carrying all injected services and
              repositories. Must not be stored in GraphState.
        checkpointer: Optional. If None, defaults to MemorySaver() (ADR-001).
        interrupt_before: Optional list of node names to interrupt before
              (used for multi-turn conversation or testing).

    Returns:
        Compiled LangGraph graph with invoke / stream / update_state interface.

    Raises:
        TypeError: if deps is not a GraphDependencies instance (includes None).
    """
    if not isinstance(deps, GraphDependencies):
        raise TypeError(
            f"build_graph requires a GraphDependencies instance, "
            f"got {type(deps).__name__!r}"
        )

    if checkpointer is None:
        checkpointer = MemorySaver()

    # ── StateGraph with Pydantic GraphState schema ────────────────────────────
    # LangGraph 1.x accepts Pydantic BaseModel as the state schema.
    # Each node receives a validated GraphState instance; partial update dicts
    # are merged back by LangGraph automatically.
    builder = StateGraph(GraphState)

    # ── Register nodes ────────────────────────────────────────────────────────
    # start_node and ending_node take state only (no deps).
    builder.add_node("start_node", start_node)
    builder.add_node("ending_node", ending_node)

    # triage_node and intent_node: no StateGuard required, wrap with deps.
    builder.add_node("triage_node", lambda s: triage_node(s, deps))
    builder.add_node("intent_node", lambda s: intent_node(s, deps))
    builder.add_node("registration_node", lambda s: registration_node(s, deps))

    # Protected nodes: StateGuard runs before node logic.
    builder.add_node(
        "credit_node", _guarded_node(credit_node, "credit_node", deps)
    )
    builder.add_node(
        "credit_interview_node",
        _guarded_node(credit_interview_node, "credit_interview_node", deps),
    )
    builder.add_node(
        "exchange_node", _guarded_node(exchange_node, "exchange_node", deps)
    )

    # ── Entry point ───────────────────────────────────────────────────────────
    builder.set_entry_point("start_node")

    # ── Conditional edges ─────────────────────────────────────────────────────
    # Edge routers already accept GraphState and return a node-name string.
    # No path_map required; LangGraph uses the returned string directly.
    builder.add_conditional_edges("start_node", route_after_start)
    builder.add_conditional_edges("triage_node", route_after_triage)
    builder.add_conditional_edges("registration_node", route_after_registration)
    builder.add_conditional_edges("intent_node", route_after_intent)
    builder.add_conditional_edges("credit_node", route_after_credit)
    builder.add_conditional_edges(
        "credit_interview_node", route_after_interview
    )
    builder.add_conditional_edges("exchange_node", route_after_exchange)

    # ── Terminal edge ─────────────────────────────────────────────────────────
    builder.add_edge("ending_node", END)

    # ── Compile ───────────────────────────────────────────────────────────────
    compile_kwargs: dict[str, Any] = {"checkpointer": checkpointer}
    if interrupt_before is not None:
        compile_kwargs["interrupt_before"] = interrupt_before

    return builder.compile(**compile_kwargs)
