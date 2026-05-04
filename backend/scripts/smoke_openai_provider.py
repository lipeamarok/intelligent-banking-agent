"""Manual controlled smoke for OpenAIProvider (single real call).

Security constraints:
- Reads OPENAI_API_KEY from environment only.
- Never prints secrets or request headers.
- Prints sanitized provider/model/content metadata only.
"""

from __future__ import annotations

import os

from app.llm.openai_provider import OpenAIProvider
from app.schemas.llm import LLMRequest


def _sanitize_content(text: str, max_len: int = 200) -> str:
    compact = " ".join((text or "").split())
    return compact[:max_len]


def main() -> int:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is not set")
        return 1

    try:
        provider = OpenAIProvider(api_key=api_key)
        request = LLMRequest(
            prompt="Classify banking intent. Return one label only.",
            structured_context={
                "allowed_intents": [
                    "credit_limit",
                    "credit_increase",
                    "credit_interview",
                    "exchange_quote",
                    "end_conversation",
                    "unknown",
                ],
                "user_message": "quero consultar meu limite",
                "constraints": ["single_label_only"],
            },
        )

        response = provider.generate(request)
    except Exception:
        print("provider=openai")
        print("error=provider_request_failed")
        return 1

    print("provider=openai")
    print(f"model={response.model}")
    print(f"content={_sanitize_content(response.content)}")
    print(f"fallback_triggered={bool(response.fallback_triggered)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
