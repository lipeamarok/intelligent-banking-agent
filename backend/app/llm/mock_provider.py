"""
MockProvider — deterministic LLM provider for testing.

Returns a configured fixed response on every generate() call.
Records all received requests for test inspection.
Never touches the network, filesystem, or environment variables.

Source of truth: ARCHITECTURE.md §7.2, TEST_PLAN.md Phase 7.
"""

from app.llm.provider import LLMProvider, LLMProviderError
from app.schemas.llm import LLMProviderName, LLMRequest, LLMResponse


class MockProvider(LLMProvider):
    """
    Deterministic LLM provider for unit and integration testing.

    Usage:
        provider = MockProvider(content="credit_limit")
        response = provider.generate(request)  # always returns "credit_limit"

        provider = MockProvider(should_fail=True)
        provider.generate(request)  # raises LLMProviderError
    """

    def __init__(
        self,
        content: str = "",
        model: str = "mock-model",
        should_fail: bool = False,
    ) -> None:
        self.content = content
        self.model = model
        self.should_fail = should_fail
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Return a configured fixed response or raise LLMProviderError.

        Raises:
            LLMProviderError: if should_fail=True.
        """
        if self.should_fail:
            raise LLMProviderError("mock provider failure")

        self.requests.append(request)
        return LLMResponse(
            content=self.content,
            provider=LLMProviderName.MOCK,
            model=self.model,
            fallback_triggered=False,
            input_tokens=None,
            output_tokens=None,
        )
