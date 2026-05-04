"""Bootstrap factories for real infrastructure dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config.settings import Settings
from app.exchange import ExchangeProvider, SearchApiExchangeProvider, SerpApiExchangeProvider
from app.graph.dependencies import GraphDependencies
from app.llm import (
    GrokProvider,
    IntentClassifier,
    LLMManager,
    OpenAIProvider,
    StructuredResponseInterpreter,
    CapabilityAdvisor,
)
from app.repositories.credit_request_repository import CreditRequestRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.score_limit_repository import ScoreLimitRepository

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REQUIRED_DATA_FILES = (
    "clientes.csv",
    "score_limite.csv",
    "solicitacoes_aumento_limite.csv",
)


@dataclass
class RepositoryBundle:
    """Concrete repositories used by graph dependencies."""

    customer_repository: CustomerRepository
    score_limit_repository: ScoreLimitRepository
    credit_request_repository: CreditRequestRepository


def create_llm_manager(settings: Settings, http_client: Any = None) -> LLMManager:
    """Build real LLM manager with Grok primary and OpenAI fallback."""
    if not settings.xai_api_key:
        raise ValueError("XAI_API_KEY is required to create Grok provider")
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required to create OpenAI provider")

    primary = GrokProvider(
        api_key=settings.xai_api_key,
        base_url=settings.xai_url,
        model=settings.primary_model,
        http_client=http_client,
    )
    fallback = OpenAIProvider(
        api_key=settings.openai_api_key,
        base_url=settings.openai_url,
        model=settings.fallback_model,
        http_client=http_client,
    )
    return LLMManager(primary_provider=primary, fallback_provider=fallback)


def create_intent_classifier(settings: Settings, http_client: Any = None) -> IntentClassifier:
    """Build real intent classifier using bootstrap-managed LLM manager."""
    manager = create_llm_manager(settings=settings, http_client=http_client)
    return IntentClassifier(manager)


def create_response_interpreter(
    settings: Settings,
    http_client: Any = None,
) -> StructuredResponseInterpreter:
    """Build constrained response interpreter using bootstrap-managed LLM manager."""
    manager = create_llm_manager(settings=settings, http_client=http_client)
    return StructuredResponseInterpreter(manager)


def create_capability_advisor(
    settings: Settings,
    http_client: Any = None,
) -> CapabilityAdvisor:
    """Build capability advisor using bootstrap-managed LLM manager."""
    manager = create_llm_manager(settings=settings, http_client=http_client)
    return CapabilityAdvisor(manager)


def create_exchange_provider(settings: Settings, http_client: Any = None) -> ExchangeProvider:
    """Build exchange provider selected by settings.exchange_provider."""
    if not settings.exchange_api_key:
        raise ValueError("EXCHANGE_API_KEY is required to create exchange provider")

    provider_name = settings.exchange_provider.lower()
    if provider_name == "searchapi":
        return SearchApiExchangeProvider(
            api_key=settings.exchange_api_key,
            base_url=settings.exchange_base_url,
            http_client=http_client,
        )

    if provider_name == "serpapi":
        return SerpApiExchangeProvider(
            api_key=settings.exchange_api_key,
            http_client=http_client,
        )

    raise ValueError(f"Unsupported exchange provider: {provider_name}")


def create_repositories(data_dir: Path | str) -> RepositoryBundle:
    """Create concrete CSV repositories from a data directory."""
    base = Path(data_dir)
    if not base.is_absolute():
        base = (_BACKEND_ROOT / base).resolve()

    if not base.exists() or not base.is_dir():
        raise ValueError(f"Missing required data directory: {base}")

    missing_files = [name for name in _REQUIRED_DATA_FILES if not (base / name).exists()]
    if missing_files:
        missing_joined = ", ".join(missing_files)
        raise ValueError(f"Missing required data files: {missing_joined}")

    return RepositoryBundle(
        customer_repository=CustomerRepository(base / "clientes.csv"),
        score_limit_repository=ScoreLimitRepository(base / "score_limite.csv"),
        credit_request_repository=CreditRequestRepository(base / "solicitacoes_aumento_limite.csv"),
    )


def create_graph_dependencies(
    settings: Settings,
    data_dir: Path | str | None = None,
    llm_http_client: Any = None,
    exchange_http_client: Any = None,
) -> GraphDependencies:
    """Create full GraphDependencies wiring with real repositories/providers."""
    effective_data_dir = data_dir if data_dir is not None else settings.data_dir
    repos = create_repositories(effective_data_dir)

    intent_classifier = create_intent_classifier(settings=settings, http_client=llm_http_client)
    response_interpreter = create_response_interpreter(
        settings=settings,
        http_client=llm_http_client,
    )
    capability_advisor = create_capability_advisor(
        settings=settings,
        http_client=llm_http_client,
    )
    exchange_provider = create_exchange_provider(settings=settings, http_client=exchange_http_client)

    return GraphDependencies(
        customer_repository=repos.customer_repository,
        score_limit_repository=repos.score_limit_repository,
        credit_request_repository=repos.credit_request_repository,
        exchange_provider=exchange_provider,
        intent_classifier=intent_classifier,
        response_interpreter=response_interpreter,
        capability_advisor=capability_advisor,
    )
