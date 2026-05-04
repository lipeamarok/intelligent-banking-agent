"""
LangGraph node implementations — Phase 6B.8 (credit_node + exchange_node added).

Implemented: start_node, triage_node, ending_node, intent_node, credit_node, exchange_node.
Remaining stub: credit_interview_node.

Source of truth: STATE_MACHINE.md sections 3.1–3.7, ARCHITECTURE.md §4.3.

Rules:
- Nodes must read/update GraphState only.
- Nodes must call services, never own business logic.
- Nodes must not write CSV directly.
- Nodes must not trust LLM output without validation.
- Nodes must return a partial state update as a plain dict.
- Nodes must not mutate the state object directly.
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

import logging
import re
from datetime import date as _date

from app.graph.dependencies import GraphDependencies
from app.graph.state import GraphState
from app.schemas.common import Intent, InterviewOfferResponse, InternalInterviewStep
from app.schemas.credit import CreditLimitRequest, CreditInterviewData
from app.services.auth_service import AuthService
from app.services.assisted_normalization_service import AssistedNormalizationService
from app.services.credit_service import CreditService
from app.services.normalizer_service import NormalizerService, NormalizationError
from app.services.registration_service import DuplicateCpfError, RegistrationService
from app.services.score_service import ScoreService
try:
    from pydantic import ValidationError
except ImportError:
    ValidationError = Exception  # type: ignore[assignment,misc]


_FOLLOWUP_CONTINUATION_ACTIONS: frozenset[str] = frozenset({
    "CREDIT_LIMIT_SHOWN",
    "CREDIT_REQUEST_APPROVED",
    "PARTIAL_INCREASE_APPROVED",
    "CREDIT_REASSESSMENT_APPROVED",
    "CREDIT_REASSESSMENT_DECLINED",
    "CREDIT_MAX_LIMIT_REACHED",
    "CREDIT_INTERVIEW_DECLINED",
    "EXCHANGE_QUOTE_SHOWN",
})

_FOLLOWUP_CONTINUATION_STATES: frozenset[str] = frozenset({
    "SHOWING_CREDIT_LIMIT",
    "CREDIT_REQUEST_APPROVED",
    "EXCHANGE_SHOWING_QUOTE",
})


def _is_short_followup_message(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    words = [word for word in text.split() if word]
    return len(words) <= 3


def _persist_approved_limit(customer, new_limit, customer_repository):
    """
    Persist an approved credit limit to clientes.csv and return an updated
    Customer with refreshed limite_credito.

    Best-effort: persistence failure does not break the user-visible flow.
    The graph still reflects the new limit in-memory so subsequent CREDIT_LIMIT
    queries within the same session show the approved value. Persistence
    errors are logged for technical analysis but do not interrupt the interaction.
    """
    if customer is None:
        return customer
    try:
        if customer_repository is not None and hasattr(customer_repository, "update_limit"):
            customer_repository.update_limit(customer.cpf, float(new_limit))
    except Exception:
        # Never break the user flow on a persistence error — log for analysis.
        logging.getLogger(__name__).exception(
            "csv_persist_failed: could not persist approved limit for cpf=%s new_limit=%s",
            getattr(customer, "cpf", "unknown"),
            new_limit,
        )
    return customer.model_copy(update={"limite_credito": float(new_limit)})


def _normalize_intent_text(value: str) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    return (
        text.replace("á", "a")
        .replace("à", "a")
        .replace("ã", "a")
        .replace("â", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )


def _classify_followup_intent_deterministically(message: str) -> Intent | None:
    text = _normalize_intent_text(message)
    if not text:
        return None

    if any(term in text for term in ("encerrar", "finalizar", "terminar", "tchau", "ate mais")):
        return Intent.END_CONVERSATION

    if any(
        term in text
        for term in (
            "cotacao",
            "cambio",
            "dolar",
            "euro",
            "usd",
            "eur",
            "moeda",
            "par",
        )
    ):
        return Intent.EXCHANGE_QUOTE

    if any(term in text for term in ("aument", "elevar", "subir")):
        return Intent.CREDIT_INCREASE

    if "limite" in text:
        return Intent.CREDIT_LIMIT

    return None


def _looks_like_capability_query(message: str) -> bool:
    """Detect meta-questions about capabilities, not executable intents."""
    text = _normalize_intent_text(message)
    if not text:
        return False
    markers = (
        "o que voce consegue fazer",
        "o que voce pode fazer",
        "como voce pode ajudar",
        "quais pares",
        "quais moedas",
        "quais cotacoes",
        "o que posso pedir",
        "quais servicos",
        "que tipo de ajuda",
    )
    return any(marker in text for marker in markers)


def _message_mentions_currency_specific_request(message: str) -> bool:
    """True when the user names a currency/code explicitly."""
    text = _normalize_intent_text(message)
    if not text:
        return False
    currency_terms = (
        "usd",
        "eur",
        "gbp",
        "jpy",
        "chf",
        "cad",
        "aud",
        "ars",
        "clp",
        "uyu",
        "mxn",
        "cny",
        "brl",
        "dolar",
        "euro",
        "libra",
        "iene",
        "franco",
        "peso",
        "real",
    )
    return any(term in text for term in currency_terms)


def _get_capability_hint_with_timeout(state: GraphState, deps: GraphDependencies) -> str | None:
    """
    Ask capability_advisor with a strict timeout to avoid hanging turns.

    Returns None on timeout/error/unsafe output so callers can fall back
    deterministically.
    """
    advisor = getattr(deps, "capability_advisor", None)
    if advisor is None or not hasattr(advisor, "advise"):
        return None

    customer = getattr(state, "current_customer", None)
    customer_name = getattr(customer, "nome", None) if customer is not None else None

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        fut = pool.submit(
            advisor.advise,
            user_message=state.last_user_input or "",
            customer_name=customer_name,
        )
        try:
            text = fut.result(timeout=1.5)
        except FuturesTimeoutError:
            fut.cancel()
            return None
        except Exception:
            return None

        return text if isinstance(text, str) and text.strip() else None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _default_capability_hint_text() -> str:
    return (
        "Posso ajudar com consulta de limite, aumento de limite e cotacao de cambio "
        "(BRL, USD, EUR, GBP, JPY, CHF, CAD, AUD, ARS, CLP, UYU, MXN, CNY)."
    )


def start_node(state: GraphState) -> dict:
    """
    Initialize session and route immediately to triage_node.

    STATE_MACHINE.md §3.1: start_node sets minimal defaults and signals
    that the next step is triage_node. It does not authenticate, call
    services, or access CSV.

    Returns a partial GraphState update dict.
    """
    if state.current_state and state.current_state != "STARTED":
        return {
            "next_step": "triage_node",
            "last_action_summary": "SESSION_CONTINUED",
        }

    return {
        "current_state": "STARTED",
        "next_step": "triage_node",
        "ended": False,
        "last_action_summary": "SESSION_STARTED",
    }


def triage_node(state: GraphState, deps: GraphDependencies) -> dict:
    """
    Authenticate user: collect CPF, birth date, call AuthService.

    STATE_MACHINE.md §3.2 flow:
    1. Ask for CPF if missing (Case A).
    2. Ask for birth date if CPF present but date missing (Case B).
    3. Guard against missing repository (Case C).
    4. Call AuthService; handle success (Case D) and failure (Case E).

    Returns a partial GraphState update dict. Does not mutate state.
    """
    if state.authenticated and state.current_customer is not None:
        current_state = state.current_state or "AUTHENTICATED"
        if current_state in {"ASKING_CPF", "ASKING_BIRTH_DATE"}:
            # Allow credential collection states to continue through triage.
            pass
        else:
            return {
                "current_state": current_state,
                "next_step": state.next_step or "intent_node",
                "last_action_summary": "AUTH_SESSION_REUSED",
            }

    # End-conversation: user may request to stop at any point during auth/registration.
    if state.last_user_input:
        if _classify_followup_intent_deterministically(state.last_user_input) == Intent.END_CONVERSATION:
            return {
                "ended": True,
                "current_state": "ENDED",
                "next_step": "ending_node",
                "last_assistant_output": "Atendimento encerrado conforme solicitado. Até logo!",
                "last_action_summary": "END_CONVERSATION_REQUESTED",
            }

    # Pass through registration states without auth processing.
    if state.current_state.startswith("REGISTRATION_"):
        return {
            "current_state": state.current_state,
            "next_step": "registration_node",
        }

    # Case A — CPF not yet collected
    if not state.cpf_candidate:
        # Detect registration intent before asking for CPF again.
        if (
            state.current_state == "ASKING_CPF"
            and state.last_user_input
            and _wants_to_register(state.last_user_input)
        ):
            return {
                "current_state": "REGISTRATION_ASKING_NAME",
                "registration_data": {},
                "next_step": "registration_node",
                "last_assistant_output": (
                    "Sem problemas! Vou ajudá-lo(a) a se cadastrar. "
                    "Para começar, qual é o seu nome completo?"
                ),
                "last_action_summary": "REGISTRATION_STARTED",
            }
        return {
            "current_state": "ASKING_CPF",
            "next_step": "triage_node",
            "last_assistant_output": (
                "Olá! Sou o assistente virtual do Banco Ágil e estou aqui para te ajudar. "
                "Para darmos continuidade ao atendimento, informe seu CPF."
            ),
            "last_action_summary": "ASKED_FOR_CPF",
        }

    # Case B — repository is required once CPF is provided
    if deps.customer_repository is None:
        return {
            "current_state": "ERROR",
            "next_step": "ending_node",
            "recoverable_error": True,
            "retry_available": False,
            "last_error": "MISSING_CUSTOMER_REPOSITORY",
            "last_assistant_output": (
                "Ocorreu uma falha técnica. Por favor, tente novamente mais tarde."
            ),
            "last_action_summary": "TRIAGE_DEPENDENCY_MISSING",
        }

    # Case C — CPF present, birth date not yet collected
    if not state.birth_date_candidate:
        customer = deps.customer_repository.find_by_cpf(state.cpf_candidate)
        if customer is None:
            next_attempts = state.auth_attempts + 1
            if next_attempts >= 3:
                return {
                    "authenticated": False,
                    "auth_attempts": next_attempts,
                    "is_blocked": True,
                    "ended": True,
                    "current_state": "ENDED",
                    "next_step": "ending_node",
                    "last_assistant_output": (
                        "Não foi possível autenticar seu acesso após as tentativas permitidas. "
                        "Para sua segurança, vou encerrar este atendimento."
                    ),
                    "last_action_summary": "AUTH_BLOCKED",
                }

            return {
                "authenticated": False,
                "auth_attempts": next_attempts,
                "cpf_candidate": None,
                "birth_date_candidate": None,
                "current_state": "ASKING_CPF",
                "next_step": "triage_node",
                "last_assistant_output": (
                    "Hmm, não consegui localizar o CPF informado em nossa base de dados. "
                    "Confira se os números estão corretos. Se você ainda não é cliente, "
                    "avise para seguirmos com as orientações de cadastro."
                ),
                "last_action_summary": "AUTH_FAILED_UNKNOWN_CPF",
            }

        if state.current_state == "ASKING_BIRTH_DATE" and state.last_user_input:
            return {
                "current_state": "ASKING_BIRTH_DATE",
                "next_step": "triage_node",
                "last_assistant_output": (
                    "Não consegui processar essa informação. "
                    "Para data de nascimento, use o formato DD-MM-AAAA, como 01-01-1990."
                ),
                "last_action_summary": "ASKED_FOR_BIRTH_DATE_RETRY",
            }

        return {
            "current_state": "ASKING_BIRTH_DATE",
            "next_step": "triage_node",
            "last_assistant_output": (
                "Agora informe sua data de nascimento no formato DD-MM-AAAA."
            ),
            "last_action_summary": "ASKED_FOR_BIRTH_DATE",
        }

    # Cases D / E — attempt authentication via AuthService
    auth_result = AuthService.authenticate(
        state.cpf_candidate,
        state.birth_date_candidate,
        deps.customer_repository,
    )

    # Case D — success
    if auth_result.success:
        customer_name = (
            auth_result.customer.nome if auth_result.customer is not None else ""
        )
        personalized = f" {customer_name}," if customer_name else ""
        return {
            "authenticated": True,
            "authenticated_cpf": state.cpf_candidate,
            "current_customer": auth_result.customer,
            "auth_attempts": 0,
            "current_state": "AUTHENTICATED",
            "next_step": "intent_node",
            "last_assistant_output": (
                f"Obrigado pelas confirmações{personalized} é um prazer ter você por aqui. "
                "Como posso ajudar agora?"
            ),
            "last_action_summary": "AUTHENTICATED",
        }

    # Case E — failure
    next_attempts = state.auth_attempts + 1

    if next_attempts >= 3:
        return {
            "authenticated": False,
            "auth_attempts": next_attempts,
            "is_blocked": True,
            "ended": True,
            "current_state": "ENDED",
            "next_step": "ending_node",
            "last_assistant_output": (
                "Não foi possível autenticar seu acesso após as tentativas permitidas. "
                "Para sua segurança, vou encerrar este atendimento."
            ),
            "last_action_summary": "AUTH_BLOCKED",
        }

    if auth_result.failure_reason == "wrong_birth_date":
        return {
            "authenticated": False,
            "auth_attempts": next_attempts,
            "birth_date_candidate": None,
            "current_state": "ASKING_BIRTH_DATE",
            "next_step": "triage_node",
            "last_assistant_output": (
                "Não consegui confirmar essa data de nascimento. "
                "Verifique e tente novamente."
            ),
            "last_action_summary": "AUTH_FAILED_WRONG_BIRTH_DATE",
        }

    # unknown_cpf or any unrecognised failure_reason
    return {
        "authenticated": False,
        "auth_attempts": next_attempts,
        "cpf_candidate": None,
        "birth_date_candidate": None,
        "current_state": "ASKING_CPF",
        "next_step": "triage_node",
        "last_assistant_output": (
            "Não consegui confirmar esses dados. Verifique as informações e tente novamente."
        ),
        "last_action_summary": "AUTH_FAILED_UNKNOWN_CPF",
    }


def intent_node(state: GraphState, deps: GraphDependencies) -> dict:
    """
    Identify user intent from last_user_input via deps.intent_classifier.

    STATE_MACHINE.md §3.3 flow:
    A. No user input → ask for clarification, do not call classifier.
    B. Classifier missing → controlled error, route to ending_node.
    C. Valid Intent (not UNKNOWN) → set intent, reset counter, route.
    D. Intent.UNKNOWN → increment counter; circuit-break at 3.
    E. Invalid classifier output → controlled error, loop back.
    F. Classifier raises exception → controlled error, loop back.

    Returns a partial GraphState update dict. Does not mutate state.
    """
    # ── Case A — no user input yet ────────────────────────────────────────────
    if not state.last_user_input or state.last_user_input.strip() == "":
        return {
            "current_state": "IDENTIFYING_INTENT",
            "next_step": "intent_node",
            "last_assistant_output": (
                "Por favor, descreva como posso ajudar você hoje."
            ),
            "last_action_summary": "ASKED_FOR_INTENT",
        }

    # ── Case A.0 — capability/meta question (priority path) ─────────────────
    if _looks_like_capability_query(state.last_user_input):
        advisor_text = _get_capability_hint_with_timeout(state, deps)
        return {
            "intent": Intent.UNKNOWN,
            "unknown_intent_count": 0,
            "current_state": "IDENTIFYING_INTENT",
            "next_step": "intent_node",
            "last_assistant_output": advisor_text or _default_capability_hint_text(),
            "last_action_summary": "CAPABILITY_ADVISED",
        }

    # ── Case A.1 — yes/no follow-up after completion prompts ─────────────────
    deterministic_followup_intent = _classify_followup_intent_deterministically(
        state.last_user_input
    )
    if (
        _is_short_followup_message(state.last_user_input)
        and deterministic_followup_intent is None
        and (
        state.last_action_summary in _FOLLOWUP_CONTINUATION_ACTIONS
        or state.current_state in _FOLLOWUP_CONTINUATION_STATES
        )
    ):
        try:
            accepted = AssistedNormalizationService.normalize_confirmation(
                state.last_user_input,
                interpreter=deps.response_interpreter,
            )
        except NormalizationError:
            accepted = None

        if accepted is True:
            return {
                "intent": Intent.UNKNOWN,
                "unknown_intent_count": 0,
                "current_state": "IDENTIFYING_INTENT",
                "next_step": "intent_node",
                "last_assistant_output": (
                    "Perfeito. Me diga como posso ajudar agora. "
                    "Você pode pedir consulta de limite, aumento de limite ou cotação de câmbio."
                ),
                "last_action_summary": "ASKED_FOR_INTENT_AFTER_FOLLOWUP",
            }

        if accepted is False:
            return {
                "intent": Intent.END_CONVERSATION,
                "unknown_intent_count": 0,
                "current_state": "ENDING",
                "next_step": "ending_node",
                "last_assistant_output": (
                    "Perfeito. Encerrando o atendimento conforme solicitado."
                ),
                "last_action_summary": "FOLLOWUP_DECLINED",
            }

    # ── Case A.2 — deterministic shortcut after follow-up prompt ────────────
    if state.last_action_summary in {"ASKED_FOR_INTENT", "ASKED_FOR_INTENT_AFTER_FOLLOWUP"}:
        deterministic_intent = _classify_followup_intent_deterministically(
            state.last_user_input
        )
        if deterministic_intent is not None:
            _INTENT_TO_NODE: dict[Intent, str] = {
                Intent.CREDIT_LIMIT: "credit_node",
                Intent.CREDIT_INCREASE: "credit_node",
                Intent.CREDIT_INTERVIEW: "credit_node",
                Intent.EXCHANGE_QUOTE: "exchange_node",
                Intent.END_CONVERSATION: "ending_node",
            }
            return {
                "intent": deterministic_intent,
                "current_state": "IDENTIFYING_INTENT",
                "next_step": _INTENT_TO_NODE.get(deterministic_intent, "intent_node"),
                "unknown_intent_count": 0,
                "last_action_summary": "INTENT_CLASSIFIED_DETERMINISTIC",
            }

    # ── Case B — classifier dependency missing ────────────────────────────────
    if deps.intent_classifier is None:
        return {
            "current_state": "ERROR",
            "next_step": "ending_node",
            "recoverable_error": True,
            "retry_available": False,
            "last_error": "MISSING_INTENT_CLASSIFIER",
            "last_assistant_output": (
                "Ocorreu uma falha técnica. Por favor, tente novamente mais tarde."
            ),
            "last_action_summary": "INTENT_DEPENDENCY_MISSING",
        }

    # ── Cases C / D / E / F — call classifier ────────────────────────────────
    classification_telemetry: dict | None = None
    try:
        classify_with_telemetry = getattr(
            deps.intent_classifier, "classify_with_telemetry", None
        )
        if callable(classify_with_telemetry):
            classified, _structured, classification_telemetry = (
                classify_with_telemetry(state.last_user_input)
            )
        else:
            classified = deps.intent_classifier.classify(state.last_user_input)
    except Exception:
        return {
            "recoverable_error": True,
            "retry_available": True,
            "intent": Intent.UNKNOWN,
            "current_state": "IDENTIFYING_INTENT",
            "next_step": "intent_node",
            "last_error": "INTENT_CLASSIFIER_ERROR",
            "last_assistant_output": (
                "Não consegui entender sua solicitação. Por favor, tente novamente."
            ),
            "last_action_summary": "INTENT_CLASSIFIER_ERROR",
        }

    # ── Case E — output is not a valid Intent enum member ─────────────────────
    if not isinstance(classified, Intent):
        return {
            "recoverable_error": True,
            "retry_available": True,
            "intent": Intent.UNKNOWN,
            "current_state": "IDENTIFYING_INTENT",
            "next_step": "intent_node",
            "last_assistant_output": (
                "Não consegui entender sua solicitação. Poderia reformular?"
            ),
            "last_action_summary": "INVALID_INTENT_CLASSIFIER_OUTPUT",
        }

    # ── Case D — UNKNOWN intent ───────────────────────────────────────────────
    if classified == Intent.UNKNOWN:
        next_count = state.unknown_intent_count + 1
        if next_count >= 3:
            return {
                "intent": Intent.UNKNOWN,
                "unknown_intent_count": next_count,
                "current_state": "ENDING",
                "next_step": "ending_node",
                "last_assistant_output": (
                    "Não foi possível identificar sua solicitação. Encerrando o atendimento."
                ),
                "last_action_summary": "UNKNOWN_INTENT_LIMIT_REACHED",
            }

        # Capability-aware free-text reply for meta-questions.
        # Bounded: ≤280 chars, single line, no markdown. Falls back to the
        # deterministic generic message when advisor is unavailable/timeout.
        advisor_text = _get_capability_hint_with_timeout(state, deps)

        if advisor_text:
            return {
                "intent": Intent.UNKNOWN,
                "unknown_intent_count": next_count,
                "current_state": "IDENTIFYING_INTENT",
                "next_step": "intent_node",
                "last_assistant_output": advisor_text,
                "last_action_summary": "UNKNOWN_INTENT_CAPABILITY_HINT",
            }

        return {
            "intent": Intent.UNKNOWN,
            "unknown_intent_count": next_count,
            "current_state": "IDENTIFYING_INTENT",
            "next_step": "intent_node",
            "last_assistant_output": (
                "Não entendi sua solicitação. Poderia esclarecer como posso ajudar?"
            ),
            "last_action_summary": "UNKNOWN_INTENT",
        }

    # ── Case C — valid known intent ───────────────────────────────────────────
    _INTENT_TO_NODE: dict[Intent, str] = {
        Intent.CREDIT_LIMIT: "credit_node",
        Intent.CREDIT_INCREASE: "credit_node",
        Intent.CREDIT_INTERVIEW: "credit_node",
        Intent.EXCHANGE_QUOTE: "exchange_node",
        Intent.END_CONVERSATION: "ending_node",
    }
    next_node = _INTENT_TO_NODE.get(classified, "intent_node")
    update: dict = {
        "intent": classified,
        "current_state": "IDENTIFYING_INTENT",
        "next_step": next_node,
        "unknown_intent_count": 0,
        "last_action_summary": "INTENT_CLASSIFIED",
    }

    # Prevent stale request reuse when coming from a prior rejected or approved
    # increase flow (do not clobber valid pre-populated requests).
    if (
        classified == Intent.CREDIT_INCREASE
        and state.current_state != "ASKING_NEW_LIMIT"
        and (bool(state.request_rejected) or state.last_action_summary == "CREDIT_REQUEST_APPROVED")
    ):
        if not any(ch.isdigit() for ch in (state.last_user_input or "")):
            update["credit_request"] = None
            update["request_rejected"] = False

    # Prevent stale quote replay only after a previous quote was shown.
    if (
        classified == Intent.EXCHANGE_QUOTE
        and state.last_action_summary == "EXCHANGE_QUOTE_SHOWN"
    ):
        if not _message_mentions_currency_specific_request(state.last_user_input or ""):
            update["exchange_request"] = None

    if classification_telemetry is not None:
        provider = classification_telemetry.get("provider")
        if provider:
            update["provider_used"] = provider
        update["fallback_triggered"] = bool(
            classification_telemetry.get("fallback_triggered")
        )
        confidence = classification_telemetry.get("confidence_bucket") or "unknown"
        update["decision_rationale"] = (
            f"intent_classified={classified.value} "
            f"confidence={confidence} "
            f"provider={provider or 'unknown'}"
        )
    return update


def credit_node(state: GraphState, deps: GraphDependencies) -> dict:
    """
    Handle credit limit consultation and credit increase requests.

    STATE_MACHINE.md §3.4 flow:
    A. Unauthenticated → controlled error, route to ending_node.
    B. authenticated but no current_customer → controlled error.
    C. Intent.CREDIT_LIMIT → show current limit, route to intent_node.
    D. Intent.CREDIT_INCREASE, no credit_request → ask for new limit.
    E. credit_request present but invalid → ask for valid limit.
    F. Missing score_limit_repository → controlled error.
    G. Missing credit_request_repository → controlled error.
    H. CreditService evaluates → approved or rejected.

    Returns a partial GraphState update dict. Does not mutate state.
    """
    # ── Case A — unauthenticated ───────────────────────────────────────────────
    if not state.authenticated:
        return {
            "recoverable_error": True,
            "retry_available": False,
            "current_state": "ERROR",
            "next_step": "ending_node",
            "last_error": "UNAUTHENTICATED_CREDIT_ACCESS",
            "last_assistant_output": (
                "Você precisa estar autenticado para acessar informações de crédito."
            ),
            "last_action_summary": "CREDIT_ACCESS_DENIED",
        }

    # ── Case B — no customer object ──────────────────────────────────────────
    if state.current_customer is None:
        return {
            "recoverable_error": True,
            "retry_available": False,
            "current_state": "ERROR",
            "next_step": "ending_node",
            "last_error": "MISSING_CURRENT_CUSTOMER",
            "last_assistant_output": (
                "Não foi possível localizar seus dados. Por favor, tente novamente mais tarde."
            ),
            "last_action_summary": "CREDIT_CUSTOMER_MISSING",
        }

    # ── Case C — consultation: show current limit ──────────────────────────────
    if state.intent == Intent.CREDIT_LIMIT:
        current_limit = CreditService.get_current_limit(state.current_customer)
        return {
            "current_state": "SHOWING_CREDIT_LIMIT",
            "next_step": "intent_node",
            "last_assistant_output": (
                f"Seu limite de crédito atual é R$ {current_limit:,.2f}. "
                "Posso ajudar com mais alguma coisa?"
            ),
            "last_action_summary": "CREDIT_LIMIT_SHOWN",
        }

    # ── Case C.05 — post-interview reassessment confirmation ───────────────
    if state.interview_complete and state.current_state == "RECALCULATING_SCORE":
        if state.credit_request is None:
            return {
                "current_state": "IDENTIFYING_INTENT",
                "next_step": "intent_node",
                "interview_complete": False,
                "last_assistant_output": (
                    "Seu score já foi atualizado. Se quiser solicitar um novo aumento, "
                    "me informe o valor desejado."
                ),
                "last_action_summary": "CREDIT_REASSESSMENT_MISSING_REQUEST",
            }

        try:
            accepted = AssistedNormalizationService.normalize_confirmation(
                state.last_user_input or "",
                interpreter=deps.response_interpreter,
            )
        except NormalizationError:
            return {
                "current_state": "RECALCULATING_SCORE",
                "next_step": "credit_node",
                "interview_complete": True,
                "credit_request": state.credit_request,
                "last_assistant_output": (
                    "Posso reavaliar o mesmo pedido com seu score atualizado. "
                    "Responda apenas sim ou não."
                ),
                "last_action_summary": "ASKED_REASSESSMENT_CONFIRMATION_RETRY",
            }

        if not accepted:
            return {
                "current_state": "IDENTIFYING_INTENT",
                "next_step": "intent_node",
                "interview_complete": False,
                "interview_step": None,
                "interview_data": {},
                "request_rejected": False,
                "credit_request": state.credit_request,
                "last_assistant_output": (
                    "Tudo bem. Seu score já foi atualizado. "
                    "Se quiser, posso ajudar com outra consulta."
                ),
                "last_action_summary": "CREDIT_REASSESSMENT_DECLINED",
            }

    # ── Case C.1 — partial increase offer response ──────────────────────────
    if state.current_state == "OFFERING_PARTIAL_INCREASE" and state.offered_partial_limit is not None:
        partial_limit = state.offered_partial_limit

        # Use LLM with negotiation-aware guidance so phrases like
        # "não consigo pelo menos 5 mil?" are read as acceptance
        try:
            accepted = AssistedNormalizationService.normalize_confirmation(
                state.last_user_input or "",
                interpreter=deps.response_interpreter,
                extra_guidance=(
                    "Context: the bank just offered the user a partial credit-limit increase. "
                    "Treat negotiation phrases, questions asking 'can I get at least X?' "
                    "and expressions of mild interest as 'accepted'. "
                    "Only map clear refusals to 'declined'."
                ),
                extra_examples={
                    "não consigo pelo menos isso?": "accepted",
                    "é o máximo?": "accepted",
                    "tá bom, aceito": "accepted",
                    "não quero tão pouco": "declined",
                    "prefiro não": "declined",
                },
            )
        except NormalizationError:
            partial_fmt = f"R$ {partial_limit:,.2f}"
            return {
                "current_state": "OFFERING_PARTIAL_INCREASE",
                "next_step": "credit_node",
                "offered_partial_limit": partial_limit,
                "last_assistant_output": (
                    f"Posso oferecer um aumento de limite para {partial_fmt}. "
                    "Você aceita essa proposta? Responda sim ou não."
                ),
                "last_action_summary": "ASKED_PARTIAL_INCREASE_CONFIRMATION_RETRY",
            }

        if accepted:
            # Accept partial offer — create and evaluate a new request for max_allowed
            if deps.score_limit_repository is None or deps.credit_request_repository is None:
                return {
                    "recoverable_error": True,
                    "retry_available": False,
                    "current_state": "ERROR",
                    "next_step": "ending_node",
                    "last_error": "MISSING_REPOSITORY",
                    "last_assistant_output": "Ocorreu uma falha técnica. Por favor, tente novamente mais tarde.",
                    "last_action_summary": "CREDIT_DEPENDENCY_MISSING",
                }
            from app.schemas.credit import CreditRequestStatus
            partial_req = CreditLimitRequest(
                cpf_cliente=state.current_customer.cpf,
                limite_atual=state.current_customer.limite_credito,
                novo_limite_solicitado=partial_limit,
                status_pedido=CreditRequestStatus.PENDENTE,
            )
            partial_result = CreditService.evaluate_limit_request(
                partial_req,
                state.current_customer,
                deps.score_limit_repository,
                deps.credit_request_repository,
            )
            if partial_result.approved:
                updated_customer = _persist_approved_limit(
                    state.current_customer,
                    partial_limit,
                    deps.customer_repository,
                )
                return {
                    "current_state": "CREDIT_REQUEST_APPROVED",
                    "next_step": "intent_node",
                    "request_rejected": False,
                    "offered_partial_limit": None,
                    "credit_request": partial_result.request.model_dump(),
                    "current_customer": updated_customer,
                    "last_assistant_output": (
                        f"Ótimo! Seu limite de crédito foi aumentado para R$ {partial_limit:,.2f}. "
                        "Posso ajudar com mais alguma coisa?"
                    ),
                    "last_action_summary": "PARTIAL_INCREASE_APPROVED",
                }
            # Unexpected rejection of partial amount — fall through to interview offer
        else:
            # Declined the partial offer → offer interview as next step
            return {
                "current_state": "OFFERING_CREDIT_INTERVIEW",
                "next_step": "credit_node",
                "request_rejected": True,
                "offered_partial_limit": None,
                "interview_offer_response": InterviewOfferResponse.UNKNOWN,
                "last_assistant_output": (
                    "Entendo. Se quiser, podemos realizar uma entrevista financeira para tentar "
                    "melhorar ainda mais o seu perfil de crédito. Deseja tentar?"
                ),
                "last_action_summary": "CREDIT_INTERVIEW_OFFERED",
            }

    # ── Case C.2 — pending interview offer response ─────────────────────────
    if (
        state.request_rejected
        and state.current_state in {"OFFERING_CREDIT_INTERVIEW", "CREDIT_REQUEST_REJECTED"}
    ):
        try:
            accepted = AssistedNormalizationService.normalize_confirmation(
                state.last_user_input or "",
                interpreter=deps.response_interpreter,
            )
        except NormalizationError:
            return {
                "current_state": "OFFERING_CREDIT_INTERVIEW",
                "next_step": "credit_node",
                "request_rejected": True,
                "interview_offer_response": InterviewOfferResponse.UNKNOWN,
                "last_assistant_output": (
                    "Para seguir, responda apenas sim ou não. "
                    "Se aceitar, iniciaremos a entrevista para tentar melhorar sua análise de crédito."
                ),
                "last_action_summary": "ASKED_INTERVIEW_CONFIRMATION_RETRY",
            }

        if accepted:
            return {
                "current_state": "OFFERING_CREDIT_INTERVIEW",
                "next_step": "credit_interview_node",
                "interview_complete": False,
                "interview_step": None,
                "interview_data": {},
                "request_rejected": True,
                "interview_offer_response": InterviewOfferResponse.ACCEPTED,
                "last_assistant_output": (
                    "Perfeito. Vamos iniciar a entrevista financeira para atualizar sua análise."
                ),
                "last_action_summary": "CREDIT_INTERVIEW_ACCEPTED",
            }

        return {
            "current_state": "IDENTIFYING_INTENT",
            "next_step": "intent_node",
            "request_rejected": False,
            "interview_offer_response": InterviewOfferResponse.DECLINED,
            "interview_step": None,
            "interview_data": {},
            "interview_complete": False,
            "credit_request": None,
            "last_assistant_output": (
                "Tudo bem. Se quiser, posso te ajudar com consulta de limite ou cotação de câmbio."
            ),
            "last_action_summary": "CREDIT_INTERVIEW_DECLINED",
        }

    # ── Cases D–I — increase request ──────────────────────────────────────────
    # Case D — no credit_request yet
    if state.credit_request is None:
        return {
            "current_state": "ASKING_NEW_LIMIT",
            "next_step": "credit_node",
            "last_assistant_output": (
                "Qual o valor do novo limite de crédito que você deseja solicitar?"
            ),
            "last_action_summary": "ASKED_FOR_NEW_LIMIT",
        }

    # Case E — validate credit_request dict into typed schema
    # P3: chat.py may emit a sentinel novo_limite_solicitado=-1.0 when the
    # user asks for "the maximum possible". Resolve it here using the
    # score-limit table before Pydantic validation.
    pending_request = dict(state.credit_request) if isinstance(state.credit_request, dict) else state.credit_request
    if (
        isinstance(pending_request, dict)
        and pending_request.get("novo_limite_solicitado") == -1.0
        and deps.score_limit_repository is not None
        and state.current_customer is not None
    ):
        try:
            max_for_score = deps.score_limit_repository.find_max_limit_for_score(
                int(state.current_customer.score_atual)
            )
            if max_for_score and max_for_score > 0:
                pending_request["novo_limite_solicitado"] = float(max_for_score)
        except Exception:
            # Fall through to validation; sentinel will be rejected as invalid.
            pass

    try:
        request = CreditLimitRequest(**pending_request)
    except (ValidationError, TypeError, ValueError):
        return {
            "recoverable_error": True,
            "retry_available": True,
            "current_state": "ASKING_NEW_LIMIT",
            "next_step": "credit_node",
            "last_error": "INVALID_CREDIT_REQUEST",
            "last_assistant_output": (
                "O valor informado não é válido. Por favor, informe um valor entre R$ 1 e R$ 1.000.000."
            ),
            "last_action_summary": "INVALID_CREDIT_REQUEST",
        }

    # Case F — missing score_limit_repository
    if deps.score_limit_repository is None:
        return {
            "recoverable_error": True,
            "retry_available": False,
            "current_state": "ERROR",
            "next_step": "ending_node",
            "last_error": "MISSING_SCORE_LIMIT_REPOSITORY",
            "last_assistant_output": (
                "Ocorreu uma falha técnica. Por favor, tente novamente mais tarde."
            ),
            "last_action_summary": "CREDIT_DEPENDENCY_MISSING",
        }

    # Case G — missing credit_request_repository
    if deps.credit_request_repository is None:
        return {
            "recoverable_error": True,
            "retry_available": False,
            "current_state": "ERROR",
            "next_step": "ending_node",
            "last_error": "MISSING_CREDIT_REQUEST_REPOSITORY",
            "last_assistant_output": (
                "Ocorreu uma falha técnica. Por favor, tente novamente mais tarde."
            ),
            "last_action_summary": "CREDIT_DEPENDENCY_MISSING",
        }

    # Cases H / I — evaluate via CreditService
    credit_result = CreditService.evaluate_limit_request(
        request,
        state.current_customer,
        deps.score_limit_repository,
        deps.credit_request_repository,
    )

    if state.interview_complete and state.current_state == "RECALCULATING_SCORE":
        if credit_result.approved:
            updated_customer = _persist_approved_limit(
                state.current_customer,
                request.novo_limite_solicitado,
                deps.customer_repository,
            )
            return {
                "current_state": "CREDIT_REQUEST_APPROVED",
                "next_step": "intent_node",
                "interview_complete": False,
                "interview_step": None,
                "interview_data": {},
                "request_rejected": False,
                "credit_request": None,
                "current_customer": updated_customer,
                "last_assistant_output": (
                    f"Reavaliei seu pedido com base no score atualizado e o aumento foi aprovado. "
                    f"Seu novo limite é R$ {request.novo_limite_solicitado:,.2f}. "
                    "Posso ajudar com mais alguma coisa?"
                ),
                "last_action_summary": "CREDIT_REASSESSMENT_APPROVED",
            }

        current_limit = CreditService.get_current_limit(state.current_customer)
        max_allowed = credit_result.max_allowed

        if max_allowed > current_limit:
            return {
                "current_state": "OFFERING_PARTIAL_INCREASE",
                "next_step": "credit_node",
                "interview_complete": False,
                "interview_step": None,
                "interview_data": {},
                "request_rejected": True,
                "offered_partial_limit": max_allowed,
                "credit_request": credit_result.request.model_dump(),
                "last_assistant_output": (
                    f"Reavaliei com o score atualizado e o valor solicitado ainda não pode ser concedido. "
                    f"Porém, consigo aumentar seu limite para R$ {max_allowed:,.2f}. Isso te atende?"
                ),
                "last_action_summary": "PARTIAL_INCREASE_OFFERED",
            }

        return {
            "current_state": "CREDIT_REQUEST_REJECTED",
            "next_step": "ending_node",
            "interview_complete": False,
            "interview_step": None,
            "interview_data": {},
            "request_rejected": False,
            "credit_request": credit_result.request.model_dump(),
            "last_assistant_output": (
                "Reavaliei seu pedido com base no score atualizado, mas este aumento ainda não pode ser concedido. "
                f"Seu limite atual permanece em R$ {current_limit:,.2f}."
            ),
            "last_action_summary": "CREDIT_REASSESSMENT_REJECTED",
        }

    if credit_result.approved:
        updated_customer = _persist_approved_limit(
            state.current_customer,
            request.novo_limite_solicitado,
            deps.customer_repository,
        )
        return {
            "current_state": "CREDIT_REQUEST_APPROVED",
            "next_step": "intent_node",
            "request_rejected": False,
            "credit_request": None,
            "current_customer": updated_customer,
            "last_assistant_output": (
                f"Sua solicitação de aumento de limite foi aprovada. "
                f"Seu novo limite é R$ {request.novo_limite_solicitado:,.2f}. "
                "Posso ajudar com mais alguma coisa?"
            ),
            "last_action_summary": "CREDIT_REQUEST_APPROVED",
        }

    current_limit = CreditService.get_current_limit(state.current_customer)
    max_allowed = credit_result.max_allowed
    requested_limit = request.novo_limite_solicitado
    if requested_limit > max_allowed and current_limit >= max_allowed:
        # Determine whether the user is at the *absolute* ceiling (top score tier)
        # or merely at the ceiling for their current score.
        # Only return CREDIT_MAX_LIMIT_REACHED when there is no higher tier to
        # unlock via an interview — otherwise always offer the interview.
        at_absolute_ceiling = False
        try:
            absolute_max = deps.score_limit_repository.find_max_limit_for_score(1000)
            at_absolute_ceiling = max_allowed >= absolute_max
        except Exception:
            # If the lookup fails we conservatively treat it as NOT at ceiling
            # so the interview offer is always surfaced.
            at_absolute_ceiling = False

        if at_absolute_ceiling:
            return {
                "current_state": "IDENTIFYING_INTENT",
                "next_step": "intent_node",
                "request_rejected": False,
                "credit_request": None,
                "last_assistant_output": (
                    f"No momento, seu perfil permite limite máximo de R$ {max_allowed:,.2f}, "
                    f"e você já está nesse valor. Posso ajudar com mais alguma coisa?"
                ),
                "last_action_summary": "CREDIT_MAX_LIMIT_REACHED",
            }

        # User is at their current-score ceiling but a higher tier exists.
        # Offer the credit interview so they can improve their score.
        return {
            "current_state": "OFFERING_CREDIT_INTERVIEW",
            "next_step": "credit_node",
            "request_rejected": True,
            "interview_offer_response": InterviewOfferResponse.UNKNOWN,
            "credit_request": credit_result.request.model_dump(),
            "last_assistant_output": (
                f"Seu perfil atual permite limite máximo de R$ {max_allowed:,.2f}, "
                f"e você já está nesse valor. Para tentar um limite maior, "
                "você pode realizar uma entrevista financeira para melhorar seu score de crédito. "
                "Deseja tentar?"
            ),
            "last_action_summary": "CREDIT_INTERVIEW_OFFERED",
        }

    return {
        "current_state": "OFFERING_CREDIT_INTERVIEW",
        "next_step": "credit_node",
        "request_rejected": True,
        "interview_offer_response": InterviewOfferResponse.UNKNOWN,
        "credit_request": credit_result.request.model_dump(),
        "last_assistant_output": (
            "Sua solicitação de aumento de limite foi recusada com base no seu perfil atual. "
            "Você gostaria de realizar uma entrevista financeira para atualizar seu score?"
        ),
        "last_action_summary": "CREDIT_INTERVIEW_OFFERED",
    }


def credit_interview_node(state: GraphState, deps: GraphDependencies) -> dict:
    """
    Conduct structured financial interview (income → employment → expenses
    → dependents → debts → complete).

    STATE_MACHINE.md §3.5 flow:
    A. Unauthenticated → controlled error, route to ending_node.
    B. No current_customer → controlled error, route to ending_node.
    C. deps.customer_repository is None → controlled error, route to ending_node.
    D. interview_step is None → initialise at INCOME, ask for income.
    E. INCOME step → normalise income, store, advance to EMPLOYMENT.
    F. EMPLOYMENT step → normalise employment, store, advance to EXPENSES.
    G. EXPENSES step → normalise expenses, store, advance to DEPENDENTS.
    H. DEPENDENTS step → parse int, store, advance to DEBTS.
    I. DEBTS step → normalise boolean, build CreditInterviewData, calculate
       score via ScoreService, update repository, route to credit_node.

    Returns a partial GraphState update dict. Does not mutate state.
    """
    # ── Case A — unauthenticated ───────────────────────────────────────────────
    if not state.authenticated:
        return {
            "current_state": "ERROR",
            "next_step": "ending_node",
            "recoverable_error": True,
            "retry_available": False,
            "last_error": "UNAUTHENTICATED_INTERVIEW_ACCESS",
            "last_assistant_output": (
                "Ocorreu uma falha técnica. Por favor, tente novamente mais tarde."
            ),
            "last_action_summary": "INTERVIEW_UNAUTHENTICATED",
        }

    # ── Case B — no current customer ──────────────────────────────────────────
    if state.current_customer is None:
        return {
            "current_state": "ERROR",
            "next_step": "ending_node",
            "recoverable_error": True,
            "retry_available": False,
            "last_error": "MISSING_CURRENT_CUSTOMER",
            "last_assistant_output": (
                "Ocorreu uma falha técnica. Por favor, tente novamente mais tarde."
            ),
            "last_action_summary": "INTERVIEW_MISSING_CUSTOMER",
        }

    # ── Case C — repository dependency missing ────────────────────────────────
    if deps.customer_repository is None:
        return {
            "current_state": "ERROR",
            "next_step": "ending_node",
            "recoverable_error": True,
            "retry_available": False,
            "last_error": "MISSING_CUSTOMER_REPOSITORY",
            "last_assistant_output": (
                "Ocorreu uma falha técnica. Por favor, tente novamente mais tarde."
            ),
            "last_action_summary": "INTERVIEW_DEPENDENCY_MISSING",
        }

    # ── Case D — interview not yet started ────────────────────────────────────
    if state.interview_step is None:
        return {
            "current_state": "CREDIT_INTERVIEW_IN_PROGRESS",
            "next_step": "credit_interview_node",
            "interview_step": InternalInterviewStep.INCOME,
            "interview_complete": False,
            "interview_data": {},
            "last_assistant_output": (
                "Vamos iniciar a análise de crédito. "
                "Qual é a sua renda mensal? (ex: R$ 5.000,00)"
            ),
            "last_action_summary": "INTERVIEW_STARTED",
        }

    user_input = state.last_user_input or ""
    current_data = dict(state.interview_data)

    # ── Case E — INCOME step ──────────────────────────────────────────────────
    if state.interview_step == InternalInterviewStep.INCOME:
        try:
            renda = NormalizerService.normalize_currency(user_input)
        except NormalizationError:
            return {
                "current_state": "CREDIT_INTERVIEW_IN_PROGRESS",
                "next_step": "credit_interview_node",
                "interview_step": InternalInterviewStep.INCOME,
                "recoverable_error": True,
                "retry_available": True,
                "last_assistant_output": (
                    "Não consegui entender o valor informado. "
                    "Por favor, informe sua renda mensal em reais (ex: 5000 ou R$ 5.000,00)."
                ),
                "last_action_summary": "INTERVIEW_INVALID_INCOME",
            }
        current_data["renda_mensal"] = renda
        return {
            "current_state": "CREDIT_INTERVIEW_IN_PROGRESS",
            "next_step": "credit_interview_node",
            "interview_step": InternalInterviewStep.EMPLOYMENT,
            "interview_data": current_data,
            "last_assistant_output": (
                "Qual é o seu tipo de emprego? "
                "(ex: CLT, autônomo, desempregado)"
            ),
            "last_action_summary": "INTERVIEW_INCOME_COLLECTED",
        }

    # ── Case F — EMPLOYMENT step ──────────────────────────────────────────────
    if state.interview_step == InternalInterviewStep.EMPLOYMENT:
        try:
            emprego = AssistedNormalizationService.normalize_employment(
                user_input,
                interpreter=deps.response_interpreter,
            )
        except NormalizationError:
            return {
                "current_state": "CREDIT_INTERVIEW_IN_PROGRESS",
                "next_step": "credit_interview_node",
                "interview_step": InternalInterviewStep.EMPLOYMENT,
                "recoverable_error": True,
                "retry_available": True,
                "last_assistant_output": (
                    "Não consegui identificar o tipo de emprego. "
                    "Por favor, informe: CLT, autônomo ou desempregado."
                ),
                "last_action_summary": "INTERVIEW_INVALID_EMPLOYMENT",
            }
        current_data["tipo_emprego"] = emprego
        return {
            "current_state": "CREDIT_INTERVIEW_IN_PROGRESS",
            "next_step": "credit_interview_node",
            "interview_step": InternalInterviewStep.EXPENSES,
            "interview_data": current_data,
            "last_assistant_output": (
                "Quais são suas despesas fixas mensais? (ex: R$ 1.500,00)"
            ),
            "last_action_summary": "INTERVIEW_EMPLOYMENT_COLLECTED",
        }

    # ── Case G — EXPENSES step ────────────────────────────────────────────────
    if state.interview_step == InternalInterviewStep.EXPENSES:
        try:
            despesas = NormalizerService.normalize_currency(user_input)
        except NormalizationError:
            return {
                "current_state": "CREDIT_INTERVIEW_IN_PROGRESS",
                "next_step": "credit_interview_node",
                "interview_step": InternalInterviewStep.EXPENSES,
                "recoverable_error": True,
                "retry_available": True,
                "last_assistant_output": (
                    "Não consegui entender o valor informado. "
                    "Por favor, informe suas despesas fixas mensais em reais."
                ),
                "last_action_summary": "INTERVIEW_INVALID_EXPENSES",
            }
        current_data["despesas_fixas_mensais"] = despesas
        return {
            "current_state": "CREDIT_INTERVIEW_IN_PROGRESS",
            "next_step": "credit_interview_node",
            "interview_step": InternalInterviewStep.DEPENDENTS,
            "interview_data": current_data,
            "last_assistant_output": (
                "Quantos dependentes você possui?"
            ),
            "last_action_summary": "INTERVIEW_EXPENSES_COLLECTED",
        }

    # ── Case H — DEPENDENTS step ──────────────────────────────────────────────
    if state.interview_step == InternalInterviewStep.DEPENDENTS:
        try:
            dependents = AssistedNormalizationService.normalize_dependents(
                user_input,
                interpreter=deps.response_interpreter,
            )
        except NormalizationError:
            return {
                "current_state": "CREDIT_INTERVIEW_IN_PROGRESS",
                "next_step": "credit_interview_node",
                "interview_step": InternalInterviewStep.DEPENDENTS,
                "recoverable_error": True,
                "retry_available": True,
                "last_assistant_output": (
                    "Por favor, informe o número de dependentes como um número inteiro (ex: 0, 1, 2)."
                ),
                "last_action_summary": "INTERVIEW_INVALID_DEPENDENTS",
            }
        current_data["numero_dependentes"] = dependents
        return {
            "current_state": "CREDIT_INTERVIEW_IN_PROGRESS",
            "next_step": "credit_interview_node",
            "interview_step": InternalInterviewStep.DEBTS,
            "interview_data": current_data,
            "last_assistant_output": (
                "Você possui dívidas ativas? (sim/não)"
            ),
            "last_action_summary": "INTERVIEW_DEPENDENTS_COLLECTED",
        }

    # ── Case I — DEBTS step (completion) ──────────────────────────────────────
    if state.interview_step == InternalInterviewStep.DEBTS:
        try:
            tem_dividas = AssistedNormalizationService.normalize_debts_answer(
                user_input,
                interpreter=deps.response_interpreter,
            )
        except NormalizationError:
            return {
                "current_state": "CREDIT_INTERVIEW_IN_PROGRESS",
                "next_step": "credit_interview_node",
                "interview_step": InternalInterviewStep.DEBTS,
                "recoverable_error": True,
                "retry_available": True,
                "last_assistant_output": (
                    "Por favor, responda sim ou não: você possui dívidas ativas?"
                ),
                "last_action_summary": "INTERVIEW_INVALID_DEBTS",
            }
        current_data["tem_dividas_ativas"] = tem_dividas

        # Build CreditInterviewData and calculate score
        try:
            interview_data_obj = CreditInterviewData(
                renda_mensal=current_data["renda_mensal"],
                tipo_emprego=current_data["tipo_emprego"],
                despesas_fixas_mensais=current_data["despesas_fixas_mensais"],
                numero_dependentes=current_data["numero_dependentes"],
                tem_dividas_ativas=current_data["tem_dividas_ativas"],
            )
        except (KeyError, ValidationError):
            return {
                "current_state": "CREDIT_INTERVIEW_IN_PROGRESS",
                "next_step": "credit_interview_node",
                "interview_step": InternalInterviewStep.DEBTS,
                "recoverable_error": True,
                "retry_available": True,
                "last_error": "INCOMPLETE_INTERVIEW_DATA",
                "last_assistant_output": (
                    "Parece que algumas informações estão faltando. Vamos continuar a entrevista."
                ),
                "last_action_summary": "INTERVIEW_INCOMPLETE_DATA",
            }

        score_result = ScoreService.calculate(interview_data_obj)
        new_score = score_result.score
        deps.customer_repository.update_score(state.current_customer.cpf, new_score)
        updated_customer = state.current_customer.model_copy(
            update={"score_atual": new_score}
        )
        return {
            "current_state": "RECALCULATING_SCORE",
            "next_step": "credit_node",
            "interview_step": InternalInterviewStep.COMPLETE,
            "interview_complete": True,
            "interview_data": {},
            "current_customer": updated_customer,
            "last_assistant_output": (
                f"Entrevista concluída! Seu score de crédito foi atualizado para {new_score}. "
                "Se desejar, posso reavaliar seu pedido de aumento de limite com base neste novo perfil."
            ),
            "last_action_summary": "INTERVIEW_COMPLETE",
        }

    # ── Fallback — unexpected step ─────────────────────────────────────────────
    return {
        "current_state": "ERROR",
        "next_step": "ending_node",
        "recoverable_error": True,
        "retry_available": False,
        "last_error": "INTERVIEW_UNEXPECTED_STEP",
        "last_assistant_output": (
            "Ocorreu um erro inesperado na entrevista. Por favor, tente novamente mais tarde."
        ),
        "last_action_summary": "INTERVIEW_UNEXPECTED_STEP",
    }


def exchange_node(state: GraphState, deps: GraphDependencies) -> dict:
    """
    Provide currency exchange quotes via injected exchange provider.

    STATE_MACHINE.md §3.6 flow:
    A. Unauthenticated → controlled error, route to ending_node.
    B. exchange_request absent → ask for currency pair, loop back.
    C. Provider missing → controlled error, route to ending_node.
    D. exchange_request invalid (missing fields) → ask for valid pair.
    E. Provider returns quote → show quote, route to intent_node.
    F. Provider raises exception → recoverable error, route to intent_node.

    Returns a partial GraphState update dict. Does not mutate state.
    """
    # ── Case A — unauthenticated ───────────────────────────────────────────────
    if not state.authenticated:
        return {
            "recoverable_error": True,
            "retry_available": False,
            "current_state": "ERROR",
            "next_step": "ending_node",
            "last_error": "UNAUTHENTICATED_EXCHANGE_ACCESS",
            "last_assistant_output": (
                "Você precisa estar autenticado para solicitar cotações de câmbio."
            ),
            "last_action_summary": "EXCHANGE_ACCESS_DENIED",
        }

    # ── Case B — no exchange_request yet ──────────────────────────────────────
    if state.exchange_request is None:
        return {
            "current_state": "EXCHANGE_ASKING_CURRENCY",
            "next_step": "exchange_node",
            "last_assistant_output": (
                "Qual par de moedas você deseja consultar? Por exemplo: BRL para USD."
            ),
            "last_action_summary": "ASKED_FOR_CURRENCY",
        }

    # ── Case C — provider missing ────────────────────────────────────────────
    if deps.exchange_provider is None:
        return {
            "recoverable_error": True,
            "retry_available": False,
            "current_state": "ERROR",
            "next_step": "ending_node",
            "last_error": "MISSING_EXCHANGE_PROVIDER",
            "last_assistant_output": (
                "O serviço de câmbio está indisponível no momento. Tente mais tarde."
            ),
            "last_action_summary": "EXCHANGE_DEPENDENCY_MISSING",
        }

    # ── Case D — validate exchange_request fields ─────────────────────────────
    base_currency = state.exchange_request.get("base_currency")
    target_currency = state.exchange_request.get("target_currency")

    if not base_currency or not target_currency:
        return {
            "recoverable_error": True,
            "retry_available": True,
            "current_state": "EXCHANGE_ASKING_CURRENCY",
            "next_step": "exchange_node",
            "last_error": "INVALID_EXCHANGE_REQUEST",
            "last_assistant_output": (
                "Por favor, informe as moedas de origem e destino. Exemplo: BRL para USD."
            ),
            "last_action_summary": "INVALID_EXCHANGE_REQUEST",
        }

    # ── Cases E / F — call provider ──────────────────────────────────────────
    try:
        quote = deps.exchange_provider.get_quote(base_currency, target_currency)
    except Exception:
        return {
            "recoverable_error": True,
            "retry_available": True,
            "current_state": "ERROR",
            "next_step": "intent_node",
            "last_error": "EXCHANGE_PROVIDER_ERROR",
            "last_assistant_output": (
                "Não foi possível obter a cotação no momento. Por favor, tente novamente."
            ),
            "last_action_summary": "EXCHANGE_PROVIDER_ERROR",
        }

    rate = quote.get("rate", "N/D")
    inverse_segment = ""
    try:
        rate_value = float(rate)
        if rate_value > 0:
            inverse_segment = f" | {target_currency} → {base_currency}: {1.0 / rate_value:.6g}"
    except (TypeError, ValueError):
        inverse_segment = ""

    return {
        "current_state": "EXCHANGE_SHOWING_QUOTE",
        "next_step": "intent_node",
        "exchange_request": {
            "base_currency": base_currency,
            "target_currency": target_currency,
            "quote": quote,
        },
        "last_assistant_output": (
            f"Cotação {base_currency} → {target_currency}: {rate}{inverse_segment}. "
            "Posso ajudar com mais alguma coisa?"
        ),
        "last_action_summary": "EXCHANGE_QUOTE_SHOWN",
    }


def ending_node(state: GraphState) -> dict:
    """
    Terminate the session gracefully.

    STATE_MACHINE.md §3.7: ending_node marks the conversation as ended,
    emits a safe closing message, and signals no further steps. It must
    not expose customer data (CPF, current_customer) in the update dict.

    Returns a partial GraphState update dict.
    """
    if state.last_action_summary == "AUTH_BLOCKED" and state.last_assistant_output:
        closing_message = state.last_assistant_output
    else:
        closing_message = (
            "Atendimento encerrado. Se precisar de algo mais, inicie uma nova conversa."
        )

    return {
        "current_state": "ENDED",
        "next_step": None,
        "ended": True,
        "last_assistant_output": closing_message,
        "last_action_summary": "SESSION_ENDED",
    }


# ── Registration helpers ───────────────────────────────────────────────────────

_REGISTRATION_INTENT_TERMS: tuple[str, ...] = (
    "nao sou cliente",
    "não sou cliente",
    "quero me cadastrar",
    "quero criar conta",
    "quero me tornar cliente",
    "tornar cliente",
    "quero ser cliente",
    "virar cliente",
    "sou novo",
    "sou nova",
    "novo cliente",
    "nova cliente",
    "ainda nao tenho cadastro",
    "ainda não tenho cadastro",
    "me cadastrar",
    "abrir conta",
    "fazer cadastro",
    "criar cadastro",
    "nao tenho conta",
    "não tenho conta",
    "primeira vez",
    "quero abrir",
    "quero criar",
)

_CANCELLATION_TERMS: tuple[str, ...] = (
    "cancelar",
    "cancel",
    "voltar",
    "desistir",
    "nao quero",
    "não quero",
    "sair",
    "encerrar",
)


def _wants_to_register(message: str) -> bool:
    """Return True when the user signals they are not yet a customer."""
    text = _normalize_intent_text(message)
    return any(term in text for term in _REGISTRATION_INTENT_TERMS)


def _wants_to_cancel(message: str) -> bool:
    """Return True when the user wants to abort an in-progress operation."""
    text = _normalize_intent_text(message)
    return any(term in text for term in _CANCELLATION_TERMS)


# ── Registration node ─────────────────────────────────────────────────────────

def registration_node(state: GraphState, deps: GraphDependencies) -> dict:
    """
    Handle the multi-step customer registration flow.

    Processes three sequential states:
      REGISTRATION_ASKING_NAME       → collect full name
      REGISTRATION_ASKING_CPF        → validate and collect CPF
      REGISTRATION_ASKING_BIRTH_DATE → validate date, create customer, authenticate

    At any step the user can cancel to return to the login flow.
    """
    current = state.current_state
    user_input = (state.last_user_input or "").strip()
    reg_data: dict = dict(state.registration_data or {})

    # ── Cancellation (any step) ───────────────────────────────────────────────
    if user_input and _wants_to_cancel(user_input):
        return {
            "current_state": "ASKING_CPF",
            "registration_data": {},
            "cpf_candidate": None,
            "birth_date_candidate": None,
            "next_step": "triage_node",
            "last_assistant_output": (
                "Tudo bem! Quando quiser, informe seu CPF para fazer login."
            ),
            "last_action_summary": "REGISTRATION_CANCELLED",
        }

    # ── Step 1: collect name ──────────────────────────────────────────────────
    if current == "REGISTRATION_ASKING_NAME":
        if not user_input:
            return {
                "current_state": "REGISTRATION_ASKING_NAME",
                "registration_data": reg_data,
                "next_step": "registration_node",
                "last_assistant_output": "Por favor, informe seu nome completo (nome e sobrenome).",
                "last_action_summary": "REGISTRATION_NAME_RETRY",
            }
        # Reject purely numeric inputs (e.g. user typed their CPF as name).
        if re.fullmatch(r"[\d\s]+", user_input):
            return {
                "current_state": "REGISTRATION_ASKING_NAME",
                "registration_data": reg_data,
                "next_step": "registration_node",
                "last_assistant_output": (
                    "Isso parece um número, não um nome. "
                    "Por favor, informe seu nome completo (ex: João da Silva)."
                ),
                "last_action_summary": "REGISTRATION_NAME_INVALID",
            }
        # Require at least one alphabetic character and at least two words.
        has_letters = any(c.isalpha() for c in user_input)
        words = [w for w in user_input.split() if w]
        if not has_letters or len(words) < 2:
            return {
                "current_state": "REGISTRATION_ASKING_NAME",
                "registration_data": reg_data,
                "next_step": "registration_node",
                "last_assistant_output": (
                    "Por favor, informe seu nome e sobrenome "
                    "(ex: Maria Souza)."
                ),
                "last_action_summary": "REGISTRATION_NAME_INVALID",
            }
        reg_data["name"] = user_input
        first = user_input.split()[0]
        return {
            "current_state": "REGISTRATION_ASKING_CPF",
            "registration_data": reg_data,
            "next_step": "registration_node",
            "last_assistant_output": (
                f"Olá, {first}! Para continuar, informe o CPF que deseja cadastrar "
                "(apenas os 11 dígitos numéricos)."
            ),
            "last_action_summary": "REGISTRATION_NAME_COLLECTED",
        }

    # ── Step 2: collect and validate CPF ─────────────────────────────────────
    if current == "REGISTRATION_ASKING_CPF":
        digits = re.sub(r"\D", "", user_input)
        if len(digits) != 11:
            return {
                "current_state": "REGISTRATION_ASKING_CPF",
                "registration_data": reg_data,
                "next_step": "registration_node",
                "last_assistant_output": (
                    "CPF inválido. Informe exatamente 11 dígitos numéricos, sem pontos ou traços."
                ),
                "last_action_summary": "REGISTRATION_CPF_INVALID",
            }

        # Check for duplicate CPF before proceeding.
        if deps.customer_repository is not None:
            try:
                existing = deps.customer_repository.find_by_cpf(digits)
            except Exception:
                existing = None
            if existing is not None:
                # CPF already registered → pivot to login flow.
                return {
                    "current_state": "ASKING_BIRTH_DATE",
                    "cpf_candidate": digits,
                    "registration_data": {},
                    "next_step": "triage_node",
                    "last_assistant_output": (
                        "Esse CPF já possui um cadastro no Banco Ágil! "
                        "Vou iniciar o login. "
                        "Por favor, informe sua data de nascimento no formato DD-MM-AAAA."
                    ),
                    "last_action_summary": "REGISTRATION_CPF_ALREADY_EXISTS",
                }

        reg_data["cpf"] = digits
        return {
            "current_state": "REGISTRATION_ASKING_BIRTH_DATE",
            "registration_data": reg_data,
            "next_step": "registration_node",
            "last_assistant_output": (
                "Ótimo! Agora informe sua data de nascimento no formato DD-MM-AAAA "
                "(ex: 15-06-1990)."
            ),
            "last_action_summary": "REGISTRATION_CPF_COLLECTED",
        }

    # ── Step 3: collect date, create customer, authenticate ───────────────────
    if current == "REGISTRATION_ASKING_BIRTH_DATE":
        try:
            birth_date = NormalizerService.normalize_date(user_input)
        except NormalizationError:
            return {
                "current_state": "REGISTRATION_ASKING_BIRTH_DATE",
                "registration_data": reg_data,
                "next_step": "registration_node",
                "last_assistant_output": (
                    "Não consegui processar essa data. "
                    "Use o formato DD-MM-AAAA, como 15-06-1990."
                ),
                "last_action_summary": "REGISTRATION_DATE_INVALID",
            }
        # Validate the date is plausible (not in the future, not impossibly old).
        today = _date.today()
        _MIN_BIRTH_YEAR = today.year - 120
        _MIN_AGE_YEARS = 16
        try:
            birth_date_obj = _date.fromisoformat(birth_date)
        except ValueError:
            birth_date_obj = None
        if birth_date_obj is None or birth_date_obj.year < _MIN_BIRTH_YEAR:
            return {
                "current_state": "REGISTRATION_ASKING_BIRTH_DATE",
                "registration_data": reg_data,
                "next_step": "registration_node",
                "last_assistant_output": (
                    "Essa data de nascimento não parece válida. "
                    "Por favor, verifique e informe novamente no formato DD-MM-AAAA."
                ),
                "last_action_summary": "REGISTRATION_DATE_IMPLAUSIBLE",
            }
        if birth_date_obj >= today:
            return {
                "current_state": "REGISTRATION_ASKING_BIRTH_DATE",
                "registration_data": reg_data,
                "next_step": "registration_node",
                "last_assistant_output": (
                    "A data de nascimento não pode ser hoje ou no futuro. "
                    "Informe sua data de nascimento no formato DD-MM-AAAA."
                ),
                "last_action_summary": "REGISTRATION_DATE_IMPLAUSIBLE",
            }
        age_years = (today - birth_date_obj).days // 365
        if age_years < _MIN_AGE_YEARS:
            return {
                "current_state": "REGISTRATION_ASKING_BIRTH_DATE",
                "registration_data": reg_data,
                "next_step": "registration_node",
                "last_assistant_output": (
                    f"É necessário ter pelo menos {_MIN_AGE_YEARS} anos para abrir uma conta. "
                    "Verifique a data informada."
                ),
                "last_action_summary": "REGISTRATION_DATE_IMPLAUSIBLE",
            }

        name = reg_data.get("name", "")
        cpf = reg_data.get("cpf", "")

        if deps.customer_repository is None or deps.score_limit_repository is None:
            return {
                "current_state": "ERROR",
                "registration_data": {},
                "recoverable_error": True,
                "retry_available": False,
                "last_error": "REGISTRATION_DEPENDENCY_MISSING",
                "last_assistant_output": (
                    "Não foi possível concluir o cadastro agora. "
                    "Por favor, tente novamente mais tarde."
                ),
                "last_action_summary": "REGISTRATION_DEPENDENCY_MISSING",
            }

        try:
            customer = RegistrationService.register_new_customer(
                name=name,
                cpf=cpf,
                birth_date=birth_date,
                customer_repository=deps.customer_repository,
                score_limit_repository=deps.score_limit_repository,
            )
        except DuplicateCpfError:
            # Rare: CPF was registered by a concurrent session between steps 2 and 3.
            return {
                "current_state": "ASKING_BIRTH_DATE",
                "cpf_candidate": cpf,
                "registration_data": {},
                "next_step": "triage_node",
                "last_assistant_output": (
                    "Esse CPF já possui um cadastro. Vou iniciar o login. "
                    "Informe sua data de nascimento no formato DD-MM-AAAA."
                ),
                "last_action_summary": "REGISTRATION_CPF_ALREADY_EXISTS",
            }
        except Exception:
            logging.getLogger(__name__).exception(
                "registration_failed: cpf=%s", cpf
            )
            return {
                "current_state": "ERROR",
                "registration_data": {},
                "recoverable_error": True,
                "retry_available": False,
                "last_error": "REGISTRATION_WRITE_FAILED",
                "last_assistant_output": (
                    "Não foi possível concluir o cadastro. "
                    "Por favor, tente novamente mais tarde."
                ),
                "last_action_summary": "REGISTRATION_FAILED",
            }

        first_name = customer.nome.split()[0] if customer.nome else "cliente"
        return {
            "authenticated": True,
            "authenticated_cpf": cpf,
            "current_customer": customer,
            "auth_attempts": 0,
            "current_state": "AUTHENTICATED",
            "registration_data": {},
            "next_step": "intent_node",
            "last_assistant_output": (
                f"Cadastro realizado com sucesso! Bem-vindo(a) ao Banco Ágil, {first_name}! "
                "Agora você já pode usar nossos serviços. Como posso ajudar?"
            ),
            "last_action_summary": "REGISTRATION_COMPLETE",
        }

    # ── Fallback (should not happen in normal flow) ───────────────────────────
    return {
        "current_state": "ASKING_CPF",
        "registration_data": {},
        "last_assistant_output": (
            "Ocorreu um problema no cadastro. Por favor, informe seu CPF para começar."
        ),
        "last_action_summary": "REGISTRATION_FALLBACK",
    }
