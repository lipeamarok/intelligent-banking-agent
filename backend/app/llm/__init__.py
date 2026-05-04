"""
app/llm — LLM provider abstraction layer.

Phase 7A exports:
  LLMProvider       — abstract base class for all provider adapters
  LLMProviderError  — controlled failure type
  MockProvider      — deterministic test double
  LLMManager        — primary/fallback orchestrator
"""

from app.llm.manager import LLMManager
from app.llm.mock_provider import MockProvider
from app.llm.intent_classifier import IntentClassifier
from app.llm.structured_response_interpreter import StructuredResponseInterpreter
from app.llm.capability_advisor import CapabilityAdvisor
from app.llm.grok_provider import GrokProvider
from app.llm.openai_provider import OpenAIProvider
from app.llm.provider import LLMProvider, LLMProviderError

__all__ = [
    "LLMProvider",
    "LLMProviderError",
    "MockProvider",
    "LLMManager",
    "IntentClassifier",
    "StructuredResponseInterpreter",
    "CapabilityAdvisor",
    "GrokProvider",
    "OpenAIProvider",
]
