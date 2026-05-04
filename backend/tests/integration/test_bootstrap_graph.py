"""Integration tests for bootstrap graph factory."""

from pathlib import Path

from app.bootstrap.graph import create_application_graph
from app.config.settings import Settings


class FakeHTTPClient:
    def __init__(self) -> None:
        self.get_calls = 0
        self.post_calls = 0

    def get(self, *args, **kwargs):
        self.get_calls += 1
        raise AssertionError("Network call should not happen during graph creation")

    def post(self, *args, **kwargs):
        self.post_calls += 1
        raise AssertionError("Network call should not happen during graph creation")


def _cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _write_min_csvs(base: Path) -> None:
    (base / "clientes.csv").write_text(
        "cpf,data_nascimento,nome,score_atual,limite_credito\n"
        "12345678901,1990-05-12,Ana Silva,720,5000.0\n"
        "98765432100,1985-11-20,Carlos Souza,540,2500.0\n",
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


def _settings() -> Settings:
    return Settings(
        xai_api_key="xai-test-key",
        openai_api_key="openai-test-key",
        exchange_api_key="exchange-test-key",
        exchange_provider="searchapi",
    )


def test_create_application_graph_returns_invokable_graph(tmp_path):
    _write_min_csvs(tmp_path)
    graph = create_application_graph(
        settings=_settings(),
        data_dir=tmp_path,
        llm_http_client=FakeHTTPClient(),
        exchange_http_client=FakeHTTPClient(),
        interrupt_before=["intent_node"],
    )

    assert hasattr(graph, "invoke")


def test_created_graph_can_authenticate_with_real_repositories_and_mocked_providers(tmp_path):
    _write_min_csvs(tmp_path)
    graph = create_application_graph(
        settings=_settings(),
        data_dir=tmp_path,
        llm_http_client=FakeHTTPClient(),
        exchange_http_client=FakeHTTPClient(),
        interrupt_before=["intent_node"],
    )

    state = dict(
        graph.invoke(
            {
                "session_id": "bootstrap-auth-01",
                "trace_id": "trace-bootstrap-auth-01",
                "cpf_candidate": "12345678901",
                "birth_date_candidate": "1990-05-12",
            },
            config=_cfg("bootstrap-auth-01-thread"),
        )
    )

    assert state.get("authenticated") is True


def test_bootstrap_graph_does_not_call_network_during_creation(tmp_path):
    _write_min_csvs(tmp_path)
    llm_client = FakeHTTPClient()
    exchange_client = FakeHTTPClient()

    _ = create_application_graph(
        settings=_settings(),
        data_dir=tmp_path,
        llm_http_client=llm_client,
        exchange_http_client=exchange_client,
        interrupt_before=["intent_node"],
    )

    assert llm_client.get_calls == 0
    assert llm_client.post_calls == 0
    assert exchange_client.get_calls == 0
    assert exchange_client.post_calls == 0
