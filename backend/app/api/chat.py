"""POST /api/v1/chat endpoint with safe GraphState mapping."""

from __future__ import annotations

import os
import re
import sys
import traceback
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from langgraph.errors import GraphRecursionError

from app.api.dependencies import GraphUnavailableError, get_app_graph, get_session_service, get_trace_id
from app.observability.logger import get_logger, log_event, sanitize_text
from app.schemas.chat import ChatMetadata, ChatRequest, ChatResponse
from app.schemas.common import PublicAgentLabel, PublicConversationState, SuggestedAction
from app.schemas.errors import ErrorCode, ErrorDetail, ErrorResponse
from app.services.normalizer_service import NormalizationError, NormalizerService
from app.services.session_service import SessionService

router = APIRouter(prefix="/api/v1", tags=["chat"])
logger = get_logger(__name__)


def _to_public_state(raw_state: str | None) -> PublicConversationState:
    if not raw_state:
        return PublicConversationState.ERROR
    if raw_state.startswith("CREDIT_INTERVIEW_"):
        return PublicConversationState.CREDIT_INTERVIEW_IN_PROGRESS
    try:
        return PublicConversationState(raw_state)
    except ValueError:
        return PublicConversationState.ERROR


def _to_public_agent(current_state: str | None, next_step: str | None) -> PublicAgentLabel:
    joined = f"{current_state or ''} {next_step or ''}".upper()
    if "EXCHANGE" in joined:
        return PublicAgentLabel.EXCHANGE
    if "OFFERING_CREDIT_INTERVIEW" in joined or "PARTIAL_INCREASE" in joined:
        return PublicAgentLabel.CREDIT
    if "RECALCULATING" in joined or "INTERVIEW" in joined:
        return PublicAgentLabel.CREDIT_INTERVIEW
    if "CREDIT" in joined:
        return PublicAgentLabel.CREDIT
    if "ERROR" in joined:
        return PublicAgentLabel.SYSTEM
    return PublicAgentLabel.TRIAGE


_GENERIC_REPLY_PHRASES: tuple[str, ...] = (
    "me diga como posso ajudar",
    "como posso ajudar",
    "o que posso fazer por voce",
    "o que posso fazer por você",
    "em que posso ajudar",
    "posso te ajudar com",
    "seja bem-vindo",
    "boas-vindas ao banco",
)

_DOMAIN_INTENT_TERMS: tuple[str, ...] = (
    "limite",
    "credito",
    "crédito",
    "cambio",
    "câmbio",
    "cotacao",
    "cotação",
    "dolar",
    "dólar",
    "euro",
    "aumento",
    "aumentar",
    "entrevista",
    "aprovado",
    "saldo",
)


def _detect_adherence_mismatch(user_input: str, reply: str) -> bool:
    """Return True when reply looks generic but user input had a detectable domain intent."""
    import unicodedata

    def _strip(text: str) -> str:
        raw = unicodedata.normalize("NFKD", text or "")
        return "".join(ch for ch in raw if not unicodedata.combining(ch)).lower()

    normalized_reply = _strip(reply)
    normalized_input = _strip(user_input)

    reply_is_generic = any(phrase in normalized_reply for phrase in _GENERIC_REPLY_PHRASES)
    input_has_domain = any(term in normalized_input for term in _DOMAIN_INTENT_TERMS)
    return reply_is_generic and input_has_domain


def _build_chat_response(state: dict[str, Any], session_id: str, trace_id: str) -> ChatResponse:
    """Map internal graph state to public ChatResponse safely."""
    retry_available = bool(state.get("retry_available", False))
    reply = state.get("last_assistant_output") or "Desculpe, não consegui processar sua solicitação."
    user_input = state.get("last_user_input", "")
    action_summary: str | None = state.get("action_summary") or state.get("last_action_summary")
    adherence_flag = _detect_adherence_mismatch(user_input, reply)
    if adherence_flag:
        logger.warning(
            "adherence_mismatch detected",
            extra={"trace_id": trace_id, "session_id": session_id},
        )
    return ChatResponse(
        session_id=session_id,
        reply=reply,
        agent=_to_public_agent(state.get("current_state"), state.get("next_step")),
        state=_to_public_state(state.get("current_state")),
        ended=bool(state.get("ended", False)),
        trace_id=trace_id,
        metadata=ChatMetadata(
            recoverable=bool(state.get("recoverable_error", False)),
            retry_available=retry_available,
            suggested_action=(SuggestedAction.RETRY if retry_available else SuggestedAction.NONE),
            last_action_summary=action_summary,
            adherence_flag=adherence_flag,
        ),
    )


def _extract_cpf_digits(message: str) -> str | None:
    digits = re.sub(r"\D", "", message)
    return digits if len(digits) == 11 else None


def _extract_currency_codes(message: str) -> tuple[str, str] | None:
    """
    Extract a (base, target) ISO 4217 currency pair from user text.

    Recognizes a broad set of PT-BR aliases so phrases like
    "peso argentino para real" or "libra para reais" map correctly.
    Pair order is the order in which currencies are mentioned.
    """
    import unicodedata

    raw = unicodedata.normalize("NFKD", message or "")
    normalized = "".join(ch for ch in raw if not unicodedata.combining(ch)).lower()

    # Multi-word aliases must be checked first so substrings don't shadow them.
    ordered_aliases: list[tuple[str, str]] = [
        ("peso argentino", "ARS"),
        ("peso uruguaio", "UYU"),
        ("peso chileno", "CLP"),
        ("peso mexicano", "MXN"),
        ("dolar canadense", "CAD"),
        ("dolar australiano", "AUD"),
        ("franco suico", "CHF"),
        ("iene japones", "JPY"),
        ("yuan chines", "CNY"),
        ("libra esterlina", "GBP"),
        ("libra", "GBP"),
        ("euro", "EUR"),
        ("dolar", "USD"),
        ("real", "BRL"),
        ("reais", "BRL"),
        ("ars", "ARS"),
        ("uyu", "UYU"),
        ("clp", "CLP"),
        ("mxn", "MXN"),
        ("cad", "CAD"),
        ("aud", "AUD"),
        ("chf", "CHF"),
        ("jpy", "JPY"),
        ("cny", "CNY"),
        ("gbp", "GBP"),
        ("eur", "EUR"),
        ("usd", "USD"),
        ("brl", "BRL"),
    ]

    found: list[tuple[int, str]] = []
    work = normalized
    for alias, code in ordered_aliases:
        idx = 0
        while True:
            position = work.find(alias, idx)
            if position == -1:
                break
            found.append((position, code))
            # Mask the matched alias so longer/shorter variants don't double-count
            work = work[:position] + (" " * len(alias)) + work[position + len(alias):]
            idx = position + len(alias)

    if not found:
        return None

    # Preserve order of mention; deduplicate consecutive same codes
    found.sort(key=lambda pair: pair[0])
    ordered_codes: list[str] = []
    for _, code in found:
        if not ordered_codes or ordered_codes[-1] != code:
            ordered_codes.append(code)

    if len(ordered_codes) >= 2:
        return ordered_codes[0], ordered_codes[1]
    # Single currency mentioned → assume the user wants it priced in BRL.
    return "BRL", ordered_codes[0]


_MAX_LIMIT_PHRASES: tuple[str, ...] = (
    "maximo possivel",
    "máximo possivel",
    "maximo possível",
    "máximo possível",
    "limite maximo",
    "limite máximo",
    "o que der",
    "o maior possivel",
    "o maior possível",
    "o maximo que puder",
    "o máximo que puder",
)


def _wants_max_possible_limit(message: str) -> bool:
    import unicodedata

    raw = unicodedata.normalize("NFKD", message or "")
    text = "".join(ch for ch in raw if not unicodedata.combining(ch)).lower().strip()
    if not text:
        return False
    return any(phrase.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u") in text for phrase in _MAX_LIMIT_PHRASES)


def _looks_like_new_exchange_request(message: str) -> bool:
    """True when the user appears to be asking for a fresh quote."""
    import unicodedata

    raw = unicodedata.normalize("NFKD", message or "")
    text = "".join(ch for ch in raw if not unicodedata.combining(ch)).lower()
    return _extract_currency_codes(text) is not None


def _looks_like_exchange_intent(message: str) -> bool:
    """Detect broad exchange intent even when no explicit pair is provided."""
    import unicodedata

    raw = unicodedata.normalize("NFKD", message or "")
    text = "".join(ch for ch in raw if not unicodedata.combining(ch)).lower().strip()
    if not text:
        return False
    terms = (
        "cambio",
        "cotacao",
        "cotar",
        "cotacao de moeda",
        "moeda",
        "dolar",
        "euro",
        "libra",
        "iene",
        "franco",
        "peso",
        "usd",
        "eur",
        "gbp",
        "jpy",
        "chf",
        "ars",
        "cad",
    )
    return any(term in text for term in terms)


def _wants_new_exchange_pair(message: str) -> bool:
    """Detect user asking for another pair, not a repeat quote."""
    import unicodedata

    raw = unicodedata.normalize("NFKD", message or "")
    text = "".join(ch for ch in raw if not unicodedata.combining(ch)).lower().strip()
    if not text:
        return False
    terms = (
        "outro par",
        "outra moeda",
        "novo par",
        "par diferente",
        "trocar par",
        "quero outro",
    )
    return any(term in text for term in terms)


def _apply_light_heuristics(state: dict[str, Any], message: str) -> dict[str, Any]:
    """Apply minimal deterministic extraction before graph invoke."""
    updated = dict(state)
    updated["last_user_input"] = message

    # ── CPF capture (P5: allow overwrite while still in ASKING_CPF) ──────────
    if not updated.get("authenticated"):
        current_state = updated.get("current_state")
        cpf = _extract_cpf_digits(message)
        if cpf and (not updated.get("cpf_candidate") or current_state == "ASKING_CPF"):
            if updated.get("cpf_candidate") != cpf:
                # New CPF supersedes a previously rejected candidate; clear birth date.
                updated["cpf_candidate"] = cpf
                updated["birth_date_candidate"] = None

    if updated.get("cpf_candidate") and not updated.get("birth_date_candidate"):
        try:
            updated["birth_date_candidate"] = NormalizerService.normalize_date(message)
        except NormalizationError:
            pass

    # ── Credit increase: numeric value or "máximo possível" (P3) ─────────────
    if updated.get("current_state") == "ASKING_NEW_LIMIT":
        customer = updated.get("current_customer")
        if isinstance(customer, dict):
            cpf_cliente = customer.get("cpf")
            limite_atual = customer.get("limite_credito")
            score_atual = customer.get("score_atual")
        else:
            cpf_cliente = getattr(customer, "cpf", None)
            limite_atual = getattr(customer, "limite_credito", None)
            score_atual = getattr(customer, "score_atual", None)

        desired_limit: float | None = None
        try:
            desired_limit = NormalizerService.normalize_currency(message)
        except NormalizationError:
            desired_limit = None

        if (
            desired_limit is None
            and _wants_max_possible_limit(message)
            and score_atual is not None
        ):
            # Best-effort: max-possible relies on the score-limit table, which
            # is repository-bound. We cannot import it here without coupling
            # the API layer to repositories, so we ask credit_node to resolve
            # it by signalling a sentinel value (-1.0) that the node turns
            # into the score_limit_repository max for the customer.
            desired_limit = -1.0

        if desired_limit is not None and cpf_cliente and limite_atual is not None:
            updated["credit_request"] = {
                "cpf_cliente": cpf_cliente,
                "limite_atual": limite_atual,
                "novo_limite_solicitado": desired_limit,
            }

    # ── Exchange: parse pair fresh and invalidate stale pair when needed ─────
    current_state = updated.get("current_state")
    if current_state == "EXCHANGE_ASKING_CURRENCY":
        currencies = _extract_currency_codes(message)
        if currencies:
            updated["exchange_request"] = {
                "base_currency": currencies[0],
                "target_currency": currencies[1],
            }
    elif (
        current_state in {"EXCHANGE_SHOWING_QUOTE", "IDENTIFYING_INTENT", "AUTHENTICATED"}
        and _looks_like_new_exchange_request(message)
    ):
        currencies = _extract_currency_codes(message)
        if currencies:
            updated["exchange_request"] = {
                "base_currency": currencies[0],
                "target_currency": currencies[1],
            }
    elif current_state in {"EXCHANGE_SHOWING_QUOTE", "IDENTIFYING_INTENT", "AUTHENTICATED"}:
        # If the user asks for exchange but does not provide an explicit pair,
        # clear stale pair so exchange_node asks again instead of replaying quote.
        if _looks_like_exchange_intent(message) and (
            _wants_new_exchange_pair(message)
            or current_state == "EXCHANGE_SHOWING_QUOTE"
            or _extract_currency_codes(message) is None
        ):
            updated["exchange_request"] = None

    return updated


def _snapshot_values_to_dict(snapshot: Any) -> dict[str, Any]:
    """Extract state values dict from LangGraph checkpoint snapshot safely."""
    values = getattr(snapshot, "values", None)
    if isinstance(values, dict):
        return dict(values)
    if values is None:
        return {}
    try:
        return dict(values)
    except Exception:
        return {}


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    session_service: SessionService = Depends(get_session_service),
    graph=Depends(get_app_graph),
    trace_id: str = Depends(get_trace_id),
) -> ChatResponse:
    """Execute one chat turn and return public-safe response envelope."""
    log_event(
        logger,
        "chat_request_received",
        trace_id=trace_id,
        session_id_present=bool(request.session_id),
        pid=os.getpid(),
        python=sys.executable,
    )

    if request.session_id:
        session_id = request.session_id
        saved = session_service.get_state(session_id)
        if saved is None:
            raise HTTPException(
                status_code=404,
                detail=ErrorResponse(
                    error=ErrorDetail(
                        code=ErrorCode.SESSION_NOT_FOUND,
                        message="Session not found",
                        trace_id=trace_id,
                        recoverable=True,
                        suggested_action=SuggestedAction.RESET,
                    )
                ).model_dump(),
            )
    else:
        session_id = session_service.create_session()
        saved = session_service.get_state(session_id) or {}

    graph_state = dict(saved.get("graph_state", {}))
    graph_state.setdefault("session_id", session_id)
    graph_state.setdefault("trace_id", trace_id)
    graph_state = _apply_light_heuristics(graph_state, request.message)
    graph_state["trace_id"] = trace_id

    config = {"configurable": {"thread_id": session_id}}
    log_event(
        logger,
        "chat_graph_invoke_start",
        trace_id=trace_id,
        session_id=session_id,
        current_state=graph_state.get("current_state"),
        pid=os.getpid(),
        python=sys.executable,
    )
    try:
        result = graph.invoke(graph_state, config=config)
        if not isinstance(result, dict):
            result = dict(result)
    except GraphUnavailableError as exc:
        log_event(
            logger,
            "chat_graph_unavailable",
            trace_id=trace_id,
            sanitized_reason=sanitize_text(getattr(exc, "reason", str(exc))),
            pid=os.getpid(),
            python=sys.executable,
        )
        raise HTTPException(
            status_code=503,
            detail=ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.INTERNAL_ERROR,
                    message="Service temporarily unavailable",
                    trace_id=trace_id,
                    recoverable=True,
                    suggested_action=SuggestedAction.RETRY,
                )
            ).model_dump(),
        )
    except GraphRecursionError as exc:
        snapshot_state: dict[str, Any] = {}
        try:
            snapshot = graph.get_state(config)
            snapshot_state = _snapshot_values_to_dict(snapshot)
        except Exception:
            snapshot_state = {}

        log_event(
            logger,
            "chat_graph_invoke_failed",
            trace_id=trace_id,
            session_id=session_id,
            exception_type=type(exc).__name__,
            sanitized_reason=sanitize_text(str(exc)),
            sanitized_traceback=sanitize_text(traceback.format_exc(limit=6)),
            current_state=snapshot_state.get("current_state"),
            pid=os.getpid(),
            python=sys.executable,
        )

        result = {
            **snapshot_state,
            "session_id": session_id,
            "trace_id": trace_id,
        }
    except Exception as exc:
        log_event(
            logger,
            "chat_graph_invoke_failed",
            trace_id=trace_id,
            session_id=session_id,
            exception_type=type(exc).__name__,
            sanitized_reason=sanitize_text(str(exc)),
            sanitized_traceback=sanitize_text(traceback.format_exc(limit=6)),
            current_state=graph_state.get("current_state"),
            pid=os.getpid(),
            python=sys.executable,
        )
        result = {
            "session_id": session_id,
            "trace_id": trace_id,
            "current_state": "ERROR",
            "ended": False,
            "recoverable_error": True,
            "retry_available": True,
            "last_assistant_output": "Desculpe, não consegui processar sua solicitação agora.",
        }

    recent_messages = list(saved.get("recent_messages", []))
    recent_messages.append({"role": "user", "content": request.message})
    recent_messages.append({"role": "assistant", "content": result.get("last_assistant_output", "")})
    recent_messages = recent_messages[-3:]

    session_service.save_state(
        session_id,
        {
            "graph_state": result,
            "recent_messages": recent_messages,
        },
    )

    return _build_chat_response(result, session_id=session_id, trace_id=trace_id)
