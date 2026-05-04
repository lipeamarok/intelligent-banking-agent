"""
LangGraph conditional edge routers — Phase 6B.1 implementation.

Each function represents one conditional edge router in the conversation graph.
Edge routers are pure functions: they read GraphState fields and return the name
of the next node as a string. They must not modify state or call services.

Source of truth: STATE_MACHINE.md section 4 (Transition Logic).

Rules:
- Edge routers must read GraphState only.
- Edge routers must return the name of the next node as a string.
- Edge routers must be pure functions with no side effects.
- Routing must never be delegated to the LLM.
"""

from app.graph.state import GraphState
from app.schemas.common import Intent, InterviewOfferResponse
from app.services.normalizer_service import NormalizationError, NormalizerService
from langgraph.graph import END


def route_after_start(state: GraphState) -> str:
    """
    After start_node: always routes to triage_node.

    STATE_MACHINE.md §4: start → triage_node
    """
    return "triage_node"


def route_after_triage(state: GraphState) -> str:
    """
    After triage_node:
    - ended == True → ending_node
    - is_blocked == True → ending_node
    - auth_attempts >= 3 → ending_node
    - current_state starts with REGISTRATION_ → registration_node
    - authenticated == True → intent_node
    - else → triage_node

    STATE_MACHINE.md §4 Triage transition table.
    """
    if state.ended:
        return "ending_node"
    if state.is_blocked:
        return "ending_node"
    if state.auth_attempts >= 3:
        return "ending_node"

    # Route registration states to registration_node.
    # Exception: if triage just *initiated* registration (REGISTRATION_STARTED),
    # end this invoke so the trigger phrase ("não sou cliente") is NOT fed
    # to registration_node as the user's name. The graph will re-enter on the
    # next user message which will contain the actual name.
    if state.current_state.startswith("REGISTRATION_"):
        if state.last_action_summary == "REGISTRATION_STARTED":
            return END
        return "registration_node"

    # Turn contract: when triage is waiting for user credentials,
    # end this invoke and wait for the next user message.
    if state.current_state in {"ASKING_CPF", "ASKING_BIRTH_DATE"}:
        return END

    if state.authenticated:
        # Pending credit follow-up questions must be answered in credit_node
        # before returning to generic intent classification.
        if state.current_state in {
            "ASKING_NEW_LIMIT",
            "OFFERING_CREDIT_INTERVIEW",
            "OFFERING_PARTIAL_INCREASE",
            "CREDIT_REQUEST_REJECTED",
            "RECALCULATING_SCORE",
        }:
            if state.current_state != "RECALCULATING_SCORE" or state.interview_complete:
                return "credit_node"

        if state.current_state == "CREDIT_INTERVIEW_IN_PROGRESS":
            return "credit_interview_node"

        # Contract: a credential-only successful auth turn must stop and
        # wait for the next user message before intent classification.
        # Accept strict DD-MM-YYYY auth inputs by normalizing last_user_input
        # before comparison.
        should_stop_after_auth = False
        if state.last_action_summary == "AUTHENTICATED" and state.birth_date_candidate:
            if state.last_user_input == state.birth_date_candidate:
                should_stop_after_auth = True
            elif state.last_user_input:
                try:
                    normalized_input = NormalizerService.normalize_date(state.last_user_input)
                    should_stop_after_auth = normalized_input == state.birth_date_candidate
                except NormalizationError:
                    should_stop_after_auth = False

        if should_stop_after_auth:
            return END
        return "intent_node"

    return "triage_node"


def route_after_intent(state: GraphState) -> str:
    """
    After intent_node:
    - ended == True → ending_node
    - is_blocked == True → ending_node
    - unknown_intent_count >= 3 → ending_node
    - intent == CREDIT_LIMIT or CREDIT_INCREASE → credit_node
    - intent == EXCHANGE_QUOTE → exchange_node
    - intent == END_CONVERSATION → ending_node
    - else (UNKNOWN, None, unrecognised) → intent_node

    STATE_MACHINE.md §4 Intent transition table.
    """
    if state.ended:
        return "ending_node"
    if state.is_blocked:
        return "ending_node"
    if state.last_action_summary in {
        "ASKED_FOR_INTENT",
        "ASKED_FOR_INTENT_AFTER_FOLLOWUP",
        "CAPABILITY_ADVISED",
        "UNKNOWN_INTENT_CAPABILITY_HINT",
    }:
        return END
    if state.unknown_intent_count >= 3:
        return "ending_node"
    if state.intent in (Intent.CREDIT_LIMIT, Intent.CREDIT_INCREASE):
        return "credit_node"
    if state.intent == Intent.CREDIT_INTERVIEW:
        return "credit_interview_node"
    if state.intent == Intent.EXCHANGE_QUOTE:
        return "exchange_node"
    if state.intent == Intent.END_CONVERSATION:
        return "ending_node"
    return "intent_node"


def route_after_credit(state: GraphState) -> str:
    """
    After credit_node:
    - ended == True → ending_node
    - is_blocked == True → ending_node
    - recoverable_error + retry_available → credit_node
    - request_rejected + offer accepted → credit_interview_node
    - request_rejected + offer declined → intent_node
    - request_rejected + offer unknown → credit_node
    - successful user-facing credit replies end the invoke to avoid same-turn loops
    - else → intent_node

    STATE_MACHINE.md §4 Credit transition table.
    """
    if state.ended:
        return "ending_node"
    if state.is_blocked:
        return "ending_node"
    if state.recoverable_error and state.retry_available:
        return "credit_node"

    if state.last_action_summary in {
        "ASKED_FOR_NEW_LIMIT",
        "CREDIT_LIMIT_SHOWN",
        "CREDIT_REQUEST_APPROVED",
        "CREDIT_MAX_LIMIT_REACHED",
        "PARTIAL_INCREASE_APPROVED",
        "PARTIAL_INCREASE_OFFERED",
        "ASKED_PARTIAL_INCREASE_CONFIRMATION_RETRY",
        "CREDIT_REASSESSMENT_APPROVED",
        "CREDIT_REASSESSMENT_REJECTED",
        "CREDIT_REASSESSMENT_DECLINED",
        "CREDIT_REASSESSMENT_MISSING_REQUEST",
        "CREDIT_INTERVIEW_OFFERED",
        "ASKED_INTERVIEW_CONFIRMATION_RETRY",
        "ASKED_REASSESSMENT_CONFIRMATION_RETRY",
        "CREDIT_INTERVIEW_DECLINED",
    }:
        return END

    if state.request_rejected:
        if state.interview_offer_response == InterviewOfferResponse.ACCEPTED:
            return "credit_interview_node"
        if state.interview_offer_response == InterviewOfferResponse.DECLINED:
            return "intent_node"
        if state.interview_offer_response == InterviewOfferResponse.UNKNOWN:
            return "credit_node"
    return "intent_node"


def route_after_interview(state: GraphState) -> str:
    """
    After credit_interview_node:
    - ended == True → ending_node
    - is_blocked == True → ending_node
        - user-facing interview question/retry replies end the invoke
            (wait for next user answer)
    - interview_complete == True → END (show completion message and wait next user turn)
        - else → credit_interview_node

    STATE_MACHINE.md §4 Interview transition table.
    """
    if state.ended:
        return "ending_node"
    if state.is_blocked:
        return "ending_node"
    if state.last_action_summary in {
        "INTERVIEW_STARTED",
        "INTERVIEW_INVALID_INCOME",
        "INTERVIEW_INCOME_COLLECTED",
        "INTERVIEW_INVALID_EMPLOYMENT",
        "INTERVIEW_EMPLOYMENT_COLLECTED",
        "INTERVIEW_INVALID_EXPENSES",
        "INTERVIEW_EXPENSES_COLLECTED",
        "INTERVIEW_INVALID_DEPENDENTS",
        "INTERVIEW_DEPENDENTS_COLLECTED",
        "INTERVIEW_INVALID_DEBTS",
        "INTERVIEW_INCOMPLETE_DATA",
    }:
        return END
    if state.interview_complete:
        return END
    return "credit_interview_node"


def route_after_exchange(state: GraphState) -> str:
    """
    After exchange_node:
    - ended == True → ending_node
    - is_blocked == True → ending_node
    - successful quote reply ends the invoke to avoid same-turn loops
    - asking for currency pair ends the invoke to await user input
    - exchange errors with next_step=intent_node end the invoke
    - else → intent_node (exchange domain always returns to intent)

    STATE_MACHINE.md §4 Exchange transition table.
    """
    if state.ended:
        return "ending_node"
    if state.is_blocked:
        return "ending_node"
    if state.last_action_summary in {
        "EXCHANGE_QUOTE_SHOWN",
        "ASKED_FOR_CURRENCY",
        "INVALID_EXCHANGE_REQUEST",
        "EXCHANGE_PROVIDER_ERROR",
        "EXCHANGE_DEPENDENCY_MISSING",
    }:
        return END
    return "intent_node"


def route_after_registration(state: GraphState) -> str:
    """
    After registration_node:
    - ended == True → ending_node
    - ERROR state → ending_node
    - authenticated == True (registration complete) → END and let triage route to intent_node
    - registration states (ASKING_NAME/CPF/DATE) → END to await next user input
    - redirected to login (ASKING_BIRTH_DATE) → END
    - else → END (safe default)
    """
    if state.ended:
        return "ending_node"
    if state.current_state == "ERROR":
        return "ending_node"
    return END
