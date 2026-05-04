"""
LLM-backed capability advisor for free-form meta-questions.

Purpose
-------
The LangGraph orchestration is deterministic and routes only Intent values
declared in `app.schemas.common.Intent`. Users, however, naturally ask
meta-questions that fall outside any single intent — for example:

    - "quais pares posso checar a cotação?"
    - "o que você consegue fazer?"
    - "vocês cotam libra esterlina?"

Without a capability-aware reply, those questions get bucketed into UNKNOWN
and the user sees a generic "não entendi" message. This service produces a
short, bounded, capability-aware answer using the existing LLM stack while
keeping the 4-agent architecture intact (it is invoked from `intent_node`
only on the UNKNOWN branch as an opt-in dependency).

Design constraints
------------------
- Output is plain text, ≤280 characters, no markdown, no system role leakage.
- Empty/invalid output returns None so the caller can fall back to the
  deterministic generic message.
- Provider errors never propagate; they degrade to None.
- The list of supported capabilities lives in CAPABILITY_BRIEF and must
  match what the rest of the system actually implements.
"""

from __future__ import annotations

from app.llm.manager import LLMManager
from app.llm.provider import LLMProviderError
from app.schemas.llm import LLMRequest

# Canonical capability brief. Keep aligned with chat.py currency parser and
# the intents declared in app.schemas.common.Intent.
CAPABILITY_BRIEF: str = (
    "Funções suportadas pelo assistente bancário:\n"
    "- Consultar o limite de crédito atual do cliente autenticado.\n"
    "- Solicitar aumento de limite (com proposta de aumento parcial e/ou "
    "entrevista financeira para reavaliação do score quando o pedido for "
    "negado).\n"
    "- Cotar câmbio entre os pares: BRL, USD, EUR, GBP, JPY, CHF, CAD, AUD, "
    "ARS, CLP, UYU, MXN, CNY.\n"
    "- Encerrar o atendimento.\n"
    "Não é possível: abrir conta, fazer transferências, emitir boletos, "
    "consultar fatura ou contratar produtos."
)

_MAX_CHARS = 280


class CapabilityAdvisor:
    """
    Free-form, bounded LLM advisor for meta-questions.

    Use only on the intent_node UNKNOWN branch when the user message looks
    like a question or capability inquiry. The advisor is opt-in via
    `GraphDependencies.capability_advisor`; when absent, callers must use
    the existing deterministic fallback message.
    """

    TASK_NAME = "capability_advice"

    def __init__(self, manager: LLMManager) -> None:
        if manager is None:
            raise ValueError("CapabilityAdvisor requires a manager; got None")
        self.manager = manager

    def advise(
        self,
        *,
        user_message: str,
        customer_name: str | None = None,
    ) -> str | None:
        """
        Produce a short capability-aware reply for the user's message.

        Returns None when the LLM call fails, the response is empty, or the
        response violates safety rules (multi-line, contains obvious prompt
        leakage, exceeds the character budget after trimming).
        """
        if not isinstance(user_message, str) or not user_message.strip():
            return None

        request = LLMRequest(
            prompt=(
                "Você é um atendente bancário em português do Brasil. "
                "O usuário fez uma pergunta livre que NÃO corresponde a uma "
                "ação executável (consultar limite, aumentar limite, cotar "
                "câmbio ou encerrar). Sua tarefa é responder em UMA OU DUAS "
                "frases curtas, sem markdown, listando apenas as capacidades "
                "que estão DENTRO da lista oficial fornecida em "
                "structured_context.capabilities. Se o usuário perguntar "
                "sobre algo fora da lista, diga claramente que não é "
                "suportado e ofereça as opções válidas. NUNCA invente "
                "funcionalidades, NUNCA cite cotações de moedas que não "
                "estejam listadas, NUNCA inclua dados pessoais. Resposta "
                "deve ter no máximo 280 caracteres."
            ),
            structured_context={
                "capabilities": CAPABILITY_BRIEF,
                "user_message": user_message,
                "customer_name": customer_name or "",
            },
            max_tokens=160,
            task=self.TASK_NAME,
        )

        try:
            response = self.manager.generate(request)
        except LLMProviderError:
            return None

        content = response.content
        if not isinstance(content, str):
            return None

        text = content.strip()
        if not text:
            return None

        # Reject obvious prompt leakage / role tokens
        lowered = text.lower()
        if any(
            marker in lowered
            for marker in ("system:", "assistant:", "structured_context", "<|")
        ):
            return None

        # Collapse to a single line (UI does not render multi-line bot output well)
        text = " ".join(text.splitlines()).strip()
        if not text:
            return None

        if len(text) > _MAX_CHARS:
            text = text[: _MAX_CHARS - 1].rstrip() + "…"

        return text
