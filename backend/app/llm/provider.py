"""
LLM provider abstract contract.

Defines the interface all LLM provider adapters must implement,
plus the controlled error type for provider failures.

No network access. No API keys. No SDK imports.
Source of truth: ARCHITECTURE.md §7.2, DECISIONS.md ADR-003.
"""

from abc import ABC, abstractmethod

from app.schemas.llm import LLMRequest, LLMResponse


class LLMProviderError(Exception):
    """Raised when an LLM provider fails to produce a response."""


class LLMProvider(ABC):
    """
    Abstract base class for all LLM provider adapters.

    Implementations:
      MockProvider  — deterministic, no network (Phase 7A)
      GrokProvider  — xAI Grok API (future phase)
      OpenAIProvider — OpenAI API (future phase)

    ARCHITECTURE.md §7.2: providers are infrastructure.
    They must not make business decisions.
    """

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Send a request to the LLM provider and return the response.

        Args:
            request: Structured LLM input (prompt + optional context).

        Returns:
            LLMResponse with content, provider name, model, and token counts.

        Raises:
            LLMProviderError: if the provider cannot produce a response.
        """
