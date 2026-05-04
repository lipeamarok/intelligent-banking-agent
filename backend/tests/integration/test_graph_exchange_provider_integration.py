"""Integration: graph uses SerpApiExchangeProvider via GraphDependencies injection."""

from app.exchange.serpapi_provider import SerpApiExchangeProvider
from app.graph.dependencies import GraphDependencies
from app.graph.graph_builder import build_graph
from app.llm.intent_classifier import IntentClassifier
from app.llm.manager import LLMManager
from app.llm.mock_provider import MockProvider
from tests.conftest import (
    ANA,
    CARLOS,
    MARINA,
    FakeCreditRequestRepository,
    FakeCustomerRepository,
    FakeScoreLimitRepository,
)


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None, raise_exc: Exception | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self._raise_exc = raise_exc

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self._raise_exc is not None:
            raise self._raise_exc
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHTTPClient:
    def __init__(self, response: FakeResponse | None = None) -> None:
        self.response = response or FakeResponse()
        self.calls: list[dict] = []

    def get(self, url: str, params: dict, timeout: float):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self.response


def _cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def test_graph_uses_real_serpapi_provider_with_fake_http_client():
    fake_http = FakeHTTPClient(
        response=FakeResponse(
            payload={
                "answer_box": {
                    "currency_converter": {
                        "exchange_rate": 5.25,
                        "from": "BRL",
                        "to": "USD",
                    }
                }
            }
        )
    )

    exchange_provider = SerpApiExchangeProvider(
        api_key="test-key",
        http_client=fake_http,
    )
    intent_classifier = IntentClassifier(
        LLMManager(primary_provider=MockProvider(content="exchange_quote"))
    )

    deps = GraphDependencies(
        customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA]),
        score_limit_repository=FakeScoreLimitRepository(),
        credit_request_repository=FakeCreditRequestRepository(),
        exchange_provider=exchange_provider,
        intent_classifier=intent_classifier,
    )

    graph = build_graph(deps, interrupt_before=["intent_node"])

    # Turn 1: authenticate
    state1 = dict(
        graph.invoke(
            {
                "session_id": "exch-real-01",
                "trace_id": "trace-exch-real-01",
                "cpf_candidate": ANA.cpf,
                "birth_date_candidate": ANA.data_nascimento,
            },
            config=_cfg("exch-real-01-thread"),
        )
    )
    assert state1.get("authenticated") is True

    # Turn 2: classify exchange intent + execute exchange_node
    graph.update_state(
        _cfg("exch-real-01-thread"),
        {
            "last_user_input": "quero cotação do dólar",
            "exchange_request": {
                "base_currency": "BRL",
                "target_currency": "USD",
            },
        },
    )
    state2 = dict(graph.invoke(None, config=_cfg("exch-real-01-thread")))
    for _ in range(3):
        if state2.get("current_state") != "AUTHENTICATED":
            break
        state2 = dict(graph.invoke(None, config=_cfg("exch-real-01-thread")))

    assert state2.get("current_state") == "EXCHANGE_SHOWING_QUOTE"
    req = state2.get("exchange_request")
    assert isinstance(req, dict)
    quote = req.get("quote")
    assert isinstance(quote, dict)
    assert quote.get("rate") == 5.25
    assert quote.get("provider") == "serpapi"

    assert len(fake_http.calls) == 1

    # Ensure no sensitive/internal dependency leakage to graph state
    for forbidden in ("api_key", "http_client", "raw_provider_response"):
        assert forbidden not in state2
        assert forbidden not in quote
