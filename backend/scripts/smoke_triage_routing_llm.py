"""Controlled smoke for post-auth triage routing with real Grok provider."""

from __future__ import annotations

from app.config.settings import load_settings_from_env
from app.llm.grok_provider import GrokProvider
from app.llm.intent_classifier import IntentClassifier
from app.llm.manager import LLMManager


class TrackingManager:
    """Proxy manager to capture the latest provider response for reporting."""

    def __init__(self, manager: LLMManager) -> None:
        self._manager = manager
        self.last_response = None

    def generate(self, request):
        self.last_response = self._manager.generate(request)
        return self.last_response


def main() -> int:
    settings = load_settings_from_env()

    if not settings.xai_api_key:
        print("smoke_triage_routing_llm: skipped (XAI_API_KEY not configured)")
        return 0

    manager = LLMManager(
        primary_provider=GrokProvider(
            api_key=settings.xai_api_key,
            base_url=settings.xai_url,
            model=settings.primary_model,
        ),
        fallback_provider=None,
    )
    tracking_manager = TrackingManager(manager)
    classifier = IntentClassifier(tracking_manager)

    print("smoke_triage_routing_llm: start")
    print("scope=post-auth-routing-only")
    print(f"configured_primary_model={settings.primary_model}")
    print("fallback_enabled=False")

    phrases = [
        "quero consultar meu limite",
        "quero aumentar meu limite",
        "quero cotação de dólar",
        "encerrar atendimento",
    ]

    call_count = 0
    for phrase in phrases:
        tracking_manager.last_response = None
        intent = classifier.classify(phrase)
        response = tracking_manager.last_response

        provider = response.provider.value if response is not None else "unknown"
        model = response.model if response is not None else "unknown"
        fallback_triggered = (
            bool(response.fallback_triggered) if response is not None else False
        )
        if response is not None:
            call_count += 1

        print(
            "phrase="
            + repr(phrase)
            + " intent="
            + intent.value
            + " provider="
            + provider
            + " model="
            + model
            + " fallback_triggered="
            + str(fallback_triggered)
        )

    print(f"real_provider_calls={call_count}")
    print("smoke_triage_routing_llm: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
