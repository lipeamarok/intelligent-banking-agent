"""
Public enums and shared types used across API contracts and internal schemas.

Source of truth: API_CONTRACT.md (public types), STATE_MACHINE.md (internal types).
"""

from enum import Enum


class PublicAgentLabel(str, Enum):
    """Public-safe agent labels exposed by the API. Must not expose LangGraph node names."""

    TRIAGE = "triage"
    CREDIT = "credit"
    CREDIT_INTERVIEW = "credit_interview"
    EXCHANGE = "exchange"
    SYSTEM = "system"


class PublicConversationState(str, Enum):
    """Public-safe conversation states exposed by the API."""

    STARTED = "STARTED"
    ASKING_CPF = "ASKING_CPF"
    ASKING_BIRTH_DATE = "ASKING_BIRTH_DATE"
    AUTHENTICATED = "AUTHENTICATED"
    IDENTIFYING_INTENT = "IDENTIFYING_INTENT"
    CREDIT_MENU = "CREDIT_MENU"
    SHOWING_CREDIT_LIMIT = "SHOWING_CREDIT_LIMIT"
    ASKING_NEW_LIMIT = "ASKING_NEW_LIMIT"
    PROCESSING_CREDIT_REQUEST = "PROCESSING_CREDIT_REQUEST"
    CREDIT_REQUEST_APPROVED = "CREDIT_REQUEST_APPROVED"
    CREDIT_REQUEST_REJECTED = "CREDIT_REQUEST_REJECTED"
    OFFERING_CREDIT_INTERVIEW = "OFFERING_CREDIT_INTERVIEW"
    OFFERING_PARTIAL_INCREASE = "OFFERING_PARTIAL_INCREASE"
    CREDIT_INTERVIEW_IN_PROGRESS = "CREDIT_INTERVIEW_IN_PROGRESS"
    RECALCULATING_SCORE = "RECALCULATING_SCORE"
    EXCHANGE_ASKING_CURRENCY = "EXCHANGE_ASKING_CURRENCY"
    EXCHANGE_FETCHING_QUOTE = "EXCHANGE_FETCHING_QUOTE"
    EXCHANGE_SHOWING_QUOTE = "EXCHANGE_SHOWING_QUOTE"
    REGISTRATION_ASKING_NAME = "REGISTRATION_ASKING_NAME"
    REGISTRATION_ASKING_CPF = "REGISTRATION_ASKING_CPF"
    REGISTRATION_ASKING_BIRTH_DATE = "REGISTRATION_ASKING_BIRTH_DATE"
    ENDING = "ENDING"
    ENDED = "ENDED"
    ERROR = "ERROR"


class SuggestedAction(str, Enum):
    """Suggested recovery or navigation action returned in API responses."""

    CONTINUE = "continue"
    RETRY = "retry"
    RESET = "reset"
    REAUTHENTICATE = "reauthenticate"
    NONE = "none"


class Intent(str, Enum):
    """Detected user intent after authentication."""

    CREDIT_LIMIT = "credit_limit"
    CREDIT_INCREASE = "credit_increase"
    CREDIT_INTERVIEW = "credit_interview"
    EXCHANGE_QUOTE = "exchange_quote"
    END_CONVERSATION = "end_conversation"
    UNKNOWN = "unknown"


class InternalInterviewStep(str, Enum):
    """Internal credit interview step tracker. Not exposed by the public API."""

    INCOME = "income"
    EMPLOYMENT = "employment"
    EXPENSES = "expenses"
    DEPENDENTS = "dependents"
    DEBTS = "debts"
    COMPLETE = "complete"


class InterviewOfferResponse(str, Enum):
    """Customer's response to the credit interview offer."""

    ACCEPTED = "accepted"
    DECLINED = "declined"
    UNKNOWN = "unknown"
