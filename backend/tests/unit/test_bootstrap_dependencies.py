"""Unit tests for bootstrap dependency factories."""

from pathlib import Path

import pytest

from app.bootstrap.dependencies import (
    RepositoryBundle,
    create_exchange_provider,
    create_graph_dependencies,
    create_intent_classifier,
    create_llm_manager,
    create_repositories,
)
from app.config.settings import Settings
from app.exchange.searchapi_provider import SearchApiExchangeProvider
from app.exchange.serpapi_provider import SerpApiExchangeProvider
from app.graph.dependencies import GraphDependencies
from app.llm.intent_classifier import IntentClassifier
from app.llm.manager import LLMManager


class FakeHTTPClient:
    def __init__(self) -> None:
        self.get_calls = 0
        self.post_calls = 0

    def get(self, *args, **kwargs):
        self.get_calls += 1
        raise AssertionError("Network call should not happen in bootstrap factory tests")

    def post(self, *args, **kwargs):
        self.post_calls += 1
        raise AssertionError("Network call should not happen in bootstrap factory tests")


@pytest.fixture
def settings_with_keys() -> Settings:
    return Settings(
        xai_api_key="xai-test-key",
        openai_api_key="openai-test-key",
        exchange_api_key="exchange-test-key",
        exchange_provider="searchapi",
    )


def _write_min_csvs(base: Path) -> None:
    (base / "clientes.csv").write_text(
        "cpf,data_nascimento,nome,score_atual,limite_credito\n"
        "12345678901,1990-05-12,Ana Silva,720,5000.0\n",
        encoding="utf-8",
    )
    (base / "score_limite.csv").write_text(
        "score_minimo,score_maximo,limite_maximo_permitido\n"
        "0,299,1000.0\n300,499,2500.0\n500,699,5000.0\n700,849,10000.0\n850,1000,20000.0\n",
        encoding="utf-8",
    )
    (base / "solicitacoes_aumento_limite.csv").write_text(
        "cpf_cliente,data_hora_solicitacao,limite_atual,novo_limite_solicitado,status_pedido\n",
        encoding="utf-8",
    )


def test_create_llm_manager_requires_xai_key(settings_with_keys):
    settings = settings_with_keys.model_copy(update={"xai_api_key": None})
    with pytest.raises(ValueError, match="XAI_API_KEY"):
        create_llm_manager(settings)


def test_create_llm_manager_requires_openai_key(settings_with_keys):
    settings = settings_with_keys.model_copy(update={"openai_api_key": None})
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        create_llm_manager(settings)


def test_create_llm_manager_creates_manager_with_fake_http_client(settings_with_keys):
    manager = create_llm_manager(settings_with_keys, http_client=FakeHTTPClient())
    assert isinstance(manager, LLMManager)


def test_create_intent_classifier_returns_classifier(settings_with_keys):
    classifier = create_intent_classifier(settings_with_keys, http_client=FakeHTTPClient())
    assert isinstance(classifier, IntentClassifier)


def test_create_exchange_provider_searchapi(settings_with_keys):
    settings = settings_with_keys.model_copy(update={"exchange_provider": "searchapi"})
    provider = create_exchange_provider(settings, http_client=FakeHTTPClient())
    assert isinstance(provider, SearchApiExchangeProvider)


def test_create_exchange_provider_serpapi(settings_with_keys):
    settings = settings_with_keys.model_copy(update={"exchange_provider": "serpapi"})
    provider = create_exchange_provider(settings, http_client=FakeHTTPClient())
    assert isinstance(provider, SerpApiExchangeProvider)


def test_create_exchange_provider_unknown_fails(settings_with_keys):
    settings = settings_with_keys.model_copy(update={"exchange_provider": "unknown"})
    with pytest.raises(ValueError, match="Unsupported exchange provider"):
        create_exchange_provider(settings, http_client=FakeHTTPClient())


def test_create_exchange_provider_requires_key(settings_with_keys):
    settings = settings_with_keys.model_copy(update={"exchange_api_key": None})
    with pytest.raises(ValueError, match="EXCHANGE_API_KEY"):
        create_exchange_provider(settings, http_client=FakeHTTPClient())


def test_create_repositories_returns_bundle(tmp_path):
    _write_min_csvs(tmp_path)
    bundle = create_repositories(tmp_path)
    assert isinstance(bundle, RepositoryBundle)
    assert bundle.customer_repository is not None
    assert bundle.score_limit_repository is not None
    assert bundle.credit_request_repository is not None


def test_create_repositories_fails_when_data_dir_missing(tmp_path):
    missing = tmp_path / "missing_data"
    with pytest.raises(ValueError, match="Missing required data directory"):
        create_repositories(missing)


def test_create_repositories_fails_when_required_csv_missing(tmp_path):
    (tmp_path / "clientes.csv").write_text(
        "cpf,data_nascimento,nome,score_atual,limite_credito\n",
        encoding="utf-8",
    )
    (tmp_path / "score_limite.csv").write_text(
        "score_minimo,score_maximo,limite_maximo_permitido\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Missing required data files"):
        create_repositories(tmp_path)


def test_create_repositories_resolves_relative_data_dir_against_backend_root(tmp_path, monkeypatch):
    fake_backend_root = tmp_path / "backend-root"
    target = fake_backend_root / "app" / "data"
    target.mkdir(parents=True)
    _write_min_csvs(target)

    monkeypatch.setattr("app.bootstrap.dependencies._BACKEND_ROOT", fake_backend_root)
    monkeypatch.chdir(tmp_path)

    bundle = create_repositories("app/data")
    assert isinstance(bundle, RepositoryBundle)


def test_create_graph_dependencies_returns_graph_dependencies(tmp_path, settings_with_keys):
    _write_min_csvs(tmp_path)
    llm_client = FakeHTTPClient()
    exchange_client = FakeHTTPClient()

    deps = create_graph_dependencies(
        settings=settings_with_keys,
        data_dir=tmp_path,
        llm_http_client=llm_client,
        exchange_http_client=exchange_client,
    )

    assert isinstance(deps, GraphDependencies)
    assert deps.customer_repository is not None
    assert deps.score_limit_repository is not None
    assert deps.credit_request_repository is not None
    assert deps.intent_classifier is not None
    assert deps.response_interpreter is not None
    assert deps.exchange_provider is not None

    assert llm_client.get_calls == 0
    assert llm_client.post_calls == 0
    assert exchange_client.get_calls == 0
    assert exchange_client.post_calls == 0


def test_create_graph_dependencies_does_not_put_settings_or_secrets_in_graph_state(tmp_path, settings_with_keys):
    _write_min_csvs(tmp_path)
    deps = create_graph_dependencies(
        settings=settings_with_keys,
        data_dir=tmp_path,
        llm_http_client=FakeHTTPClient(),
        exchange_http_client=FakeHTTPClient(),
    )

    assert isinstance(deps, GraphDependencies)
    assert not hasattr(deps, "settings")
