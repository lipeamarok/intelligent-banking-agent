"""
LLM provider request/response contracts.

No LLM calls, no provider implementation — data contracts only.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class LLMProviderName(str, Enum):
    """Supported LLM provider identifiers."""

    GROK = "grok"
    OPENAI = "openai"
    MOCK = "mock"


class LLMRequest(BaseModel):
    """Input contract sent to an LLM provider adapter."""

    prompt: str
    structured_context: dict[str, Any] = Field(default_factory=dict)
    max_tokens: int | None = None
    # Optional task tag used by observability and routing telemetry.
    # Must not influence provider behavior; only labels logs and metrics.
    task: str | None = None


class LLMResponse(BaseModel):
    """Output contract returned by an LLM provider adapter."""

    content: str
    provider: LLMProviderName
    model: str
    fallback_triggered: bool = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    # Latency of the provider call as observed by LLMManager. Optional.
    latency_ms: float | None = None


ConfidenceBucket = Literal["high", "medium", "low"]


class IntentClassification(BaseModel):
    """
    Structured intent classification result for AI engineering observability.

    Returned alongside the chosen Intent value by classify_with_telemetry().
    Captures whether the model output was directly usable, ambiguous, or had
    to be rejected; lets the orchestrator decide between routing and
    requesting clarification without exposing raw LLM content.
    """

    intent: str
    confidence_bucket: ConfidenceBucket = "low"
    ambiguous: bool = False
    should_clarify: bool = False
    safe_rationale: str | None = None

