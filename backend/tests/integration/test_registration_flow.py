"""Integration tests for the registration flow through the LangGraph pipeline."""

import pytest

from app.graph.dependencies import GraphDependencies
from app.graph.graph_builder import build_graph
from app.schemas.common import Intent
from tests.conftest import (
    ANA,
    CARLOS,
    MARINA,
    FakeCreditRequestRepository,
    FakeCustomerRepository,
    FakeExchangeProvider,
    FakeIntentClassifier,
    FakeScoreLimitRepository,
    make_graph_state,
)


def _make_deps() -> GraphDependencies:
    return GraphDependencies(
        customer_repository=FakeCustomerRepository([ANA, CARLOS, MARINA]),
        score_limit_repository=FakeScoreLimitRepository(),
        credit_request_repository=FakeCreditRequestRepository(),
        exchange_provider=FakeExchangeProvider(),
        intent_classifier=FakeIntentClassifier(Intent.END_CONVERSATION),
    )


@pytest.fixture(scope="module")
def graph():
    return build_graph(_make_deps())


def _cfg(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def _state(**kwargs) -> dict:
    return make_graph_state(**kwargs).model_dump()


class TestTriageDetectsRegistrationIntent:
    def test_nao_sou_cliente_triggers_registration_flow(self, graph):
        # Triage detects intent → sets REGISTRATION_ASKING_NAME and asks for name.
        # route_after_triage returns END so the trigger phrase is NOT fed as name.
        result = graph.invoke(
            _state(current_state="ASKING_CPF", last_user_input="não sou cliente"),
            _cfg("reg-intent-1"),
        )
        assert result["current_state"] == "REGISTRATION_ASKING_NAME"
        assert result.get("last_action_summary") == "REGISTRATION_STARTED"

    def test_quero_me_cadastrar_triggers_registration_flow(self, graph):
        result = graph.invoke(
            _state(current_state="ASKING_CPF", last_user_input="quero me cadastrar"),
            _cfg("reg-intent-2"),
        )
        assert result["current_state"] == "REGISTRATION_ASKING_NAME"

    def test_normal_cpf_input_does_not_trigger_registration(self, graph):
        result = graph.invoke(
            _state(current_state="ASKING_CPF", last_user_input="12345678901"),
            _cfg("reg-intent-3"),
        )
        assert not result["current_state"].startswith("REGISTRATION_")


class TestRegistrationNodeStepByStep:
    def test_collecting_name_advances_to_asking_cpf(self, graph):
        result = graph.invoke(
            _state(current_state="REGISTRATION_ASKING_NAME", last_user_input="João da Silva", registration_data={}),
            _cfg("reg-name-1"),
        )
        assert result["current_state"] == "REGISTRATION_ASKING_CPF"
        assert result["registration_data"].get("name") == "João da Silva"

    def test_invalid_cpf_stays_asking_cpf(self, graph):
        result = graph.invoke(
            _state(current_state="REGISTRATION_ASKING_CPF", last_user_input="123", registration_data={"name": "João"}),
            _cfg("reg-cpf-invalid"),
        )
        assert result["current_state"] == "REGISTRATION_ASKING_CPF"
        assert result.get("last_assistant_output")

    def test_valid_cpf_advances_to_asking_birth_date(self, graph):
        result = graph.invoke(
            _state(current_state="REGISTRATION_ASKING_CPF", last_user_input="33344455566", registration_data={"name": "João Novo"}),
            _cfg("reg-cpf-valid"),
        )
        assert result["current_state"] == "REGISTRATION_ASKING_BIRTH_DATE"
        assert result["registration_data"].get("cpf") == "33344455566"

    def test_duplicate_cpf_pivots_to_login(self, graph):
        result = graph.invoke(
            _state(current_state="REGISTRATION_ASKING_CPF", last_user_input="12345678901", registration_data={"name": "Cópia Ana"}),
            _cfg("reg-dup-cpf"),
        )
        assert result["current_state"] in {"ASKING_CPF", "ASKING_BIRTH_DATE"}

    def test_cancellation_during_registration_returns_to_asking_cpf(self, graph):
        result = graph.invoke(
            _state(current_state="REGISTRATION_ASKING_NAME", last_user_input="cancelar", registration_data={}),
            _cfg("reg-cancel"),
        )
        assert result["current_state"] == "ASKING_CPF"


class TestRegistrationFullFlow:
    def test_full_registration_authenticates_user(self, graph):
        """Happy path: name → CPF → date → authenticated (3 separate invocations)."""
        cfg = _cfg("reg-full-1")

        # Step 1: Provide name
        r1 = graph.invoke(
            _state(current_state="REGISTRATION_ASKING_NAME", last_user_input="Carlos Novo", registration_data={}),
            cfg,
        )
        assert r1["current_state"] == "REGISTRATION_ASKING_CPF"

        # Step 2: Provide a unique CPF (not in FakeCustomerRepository)
        r2 = graph.invoke(
            _state(current_state="REGISTRATION_ASKING_CPF", last_user_input="11199900088", registration_data=r1["registration_data"]),
            cfg,
        )
        assert r2["current_state"] == "REGISTRATION_ASKING_BIRTH_DATE"

        # Step 3: Provide birth date (DD-MM-YYYY format) → should authenticate
        r3 = graph.invoke(
            _state(current_state="REGISTRATION_ASKING_BIRTH_DATE", last_user_input="15-06-1992", registration_data=r2["registration_data"]),
            cfg,
        )
        assert r3["current_state"] == "AUTHENTICATED"
        assert r3["authenticated"] is True
        assert r3["current_customer"] is not None
        cc = r3["current_customer"]
        cpf = cc["cpf"] if isinstance(cc, dict) else cc.cpf
        assert cpf == "11199900088"


class TestRegistrationInputValidation:
    """Validate that registration_node rejects clearly invalid inputs."""

    def test_numeric_name_is_rejected(self, graph):
        """A CPF or pure number entered as name must be refused."""
        result = graph.invoke(
            _state(current_state="REGISTRATION_ASKING_NAME", last_user_input="74185296300", registration_data={}),
            _cfg("reg-val-name-1"),
        )
        assert result["current_state"] == "REGISTRATION_ASKING_NAME"
        assert result.get("last_action_summary") == "REGISTRATION_NAME_INVALID"

    def test_single_word_name_is_rejected(self, graph):
        """A single-word name (no surname) must be refused."""
        result = graph.invoke(
            _state(current_state="REGISTRATION_ASKING_NAME", last_user_input="Carlos", registration_data={}),
            _cfg("reg-val-name-2"),
        )
        assert result["current_state"] == "REGISTRATION_ASKING_NAME"
        assert result.get("last_action_summary") == "REGISTRATION_NAME_INVALID"

    def test_valid_full_name_accepted(self, graph):
        """First-name + surname must be accepted."""
        result = graph.invoke(
            _state(current_state="REGISTRATION_ASKING_NAME", last_user_input="Carlos Novo", registration_data={}),
            _cfg("reg-val-name-3"),
        )
        assert result["current_state"] == "REGISTRATION_ASKING_CPF"

    def test_ancient_birth_date_rejected(self, graph):
        """A birth year like 1830 must be refused as implausible."""
        result = graph.invoke(
            _state(current_state="REGISTRATION_ASKING_BIRTH_DATE", last_user_input="01-01-1830",
                   registration_data={"name": "Carlos Novo", "cpf": "11199900088"}),
            _cfg("reg-val-date-1"),
        )
        assert result["current_state"] == "REGISTRATION_ASKING_BIRTH_DATE"
        assert result.get("last_action_summary") == "REGISTRATION_DATE_IMPLAUSIBLE"

    def test_future_birth_date_rejected(self, graph):
        """A birth date in the future must be refused."""
        result = graph.invoke(
            _state(current_state="REGISTRATION_ASKING_BIRTH_DATE", last_user_input="01-01-2099",
                   registration_data={"name": "Carlos Novo", "cpf": "11199900088"}),
            _cfg("reg-val-date-2"),
        )
        assert result["current_state"] == "REGISTRATION_ASKING_BIRTH_DATE"
        assert result.get("last_action_summary") == "REGISTRATION_DATE_IMPLAUSIBLE"

    def test_under_minimum_age_rejected(self, graph):
        """A birth date less than 16 years ago must be refused."""
        from datetime import date
        young = date.today().replace(year=date.today().year - 5)
        result = graph.invoke(
            _state(current_state="REGISTRATION_ASKING_BIRTH_DATE",
                   last_user_input=f"{young.day:02d}-{young.month:02d}-{young.year}",
                   registration_data={"name": "Carlos Novo", "cpf": "11199900088"}),
            _cfg("reg-val-date-3"),
        )
        assert result["current_state"] == "REGISTRATION_ASKING_BIRTH_DATE"
        assert result.get("last_action_summary") == "REGISTRATION_DATE_IMPLAUSIBLE"

    def test_wants_to_register_tornar_cliente(self, graph):
        """'quero me tornar cliente' must trigger the registration flow."""
        result = graph.invoke(
            _state(current_state="ASKING_CPF", last_user_input="quero me tornar cliente"),
            _cfg("reg-val-intent-1"),
        )
        assert result["current_state"] == "REGISTRATION_ASKING_NAME"
        assert result.get("last_action_summary") == "REGISTRATION_STARTED"

