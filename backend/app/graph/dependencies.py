"""
Dependency injection container for LangGraph nodes — Phase 6B.3+.

GraphDependencies holds all injectable dependencies for domain nodes.
It is NOT stored inside GraphState. It is passed as an explicit argument
to each domain node at call time.

ARCHITECTURE.md §3.4: Nodes coordinate work. Services decide outcomes.
ARCHITECTURE.md §3.5 invariant #5: Repository layer must isolate persistence.

Rules:
- GraphDependencies must not import concrete repository implementations.
- GraphDependencies must not import LLM providers.
- GraphDependencies must not load .env or access the filesystem.
- GraphState must remain serializable and must never carry GraphDependencies.
- All fields are optional (Any | None) so test fakes can be injected freely.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class GraphDependencies:
    """
    Injectable dependencies for LangGraph domain nodes.

    All fields are optional to allow partial injection in unit tests
    and to defer wiring of real implementations to the application
    startup phase.

    Domain nodes must verify that required deps are present before
    calling services. Missing deps should produce a controlled error,
    not an AttributeError or ImportError.

    Fields:
        customer_repository:      Provides find_by_cpf / update_score.
        score_limit_repository:   Provides find_max_limit_for_score.
        credit_request_repository: Provides append.
        exchange_provider:        Provides currency quote lookup.
        intent_classifier:        Provides deterministic intent fallback.
        response_interpreter:     Provides constrained LLM normalization fallback.
        capability_advisor:       Optional LLM advisor for free-form
                                  meta-questions on the UNKNOWN intent path.
                                  When None, intent_node falls back to the
                                  deterministic generic clarification message.
    """

    customer_repository: Any | None = None
    score_limit_repository: Any | None = None
    credit_request_repository: Any | None = None
    exchange_provider: Any | None = None
    intent_classifier: Any | None = None
    response_interpreter: Any | None = None
    capability_advisor: Any | None = None
