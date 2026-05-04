"""Grok provider adapter using chat/completions-style HTTP payloads."""

import json
from typing import Any

from app.llm.provider import LLMProvider, LLMProviderError
from app.schemas.llm import LLMProviderName, LLMRequest, LLMResponse


class GrokProvider(LLMProvider):
    """HTTP provider adapter for xAI Grok-style chat completions."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.x.ai/v1/chat/completions",
        model: str = "grok-4-1-fast",
        http_client: Any = None,
        timeout: float = 15.0,
    ) -> None:
        if not isinstance(api_key, str) or api_key.strip() == "":
            raise ValueError("GrokProvider requires a non-empty api_key")

        self._api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self._http_client = http_client if http_client is not None else self._build_default_client()

    def _build_default_client(self) -> Any:
        try:
            import httpx  # type: ignore
        except Exception as exc:
            raise LLMProviderError("HTTP client unavailable for GrokProvider") from exc
        return httpx.Client()

    def _build_messages(self, request: LLMRequest) -> list[dict[str, str]]:
        structured = json.dumps(request.structured_context, ensure_ascii=True, sort_keys=True)
        user_content = f"Prompt:\n{request.prompt}\n\nStructuredContext:\n{structured}"
        return [
            {
                "role": "system",
                "content": (
                    "You are an intent-support assistant. "
                    "Return only the requested output format."
                ),
            },
            {"role": "user", "content": user_content},
        ]

    def generate(self, request: LLMRequest) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._build_messages(request),
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = self._http_client.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise LLMProviderError("Grok provider request failed") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise LLMProviderError("Grok provider returned malformed response") from exc

        if not isinstance(content, str) or content.strip() == "":
            raise LLMProviderError("Grok provider returned empty content")

        usage = data.get("usage") if isinstance(data, dict) else None
        prompt_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
        completion_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None

        return LLMResponse(
            content=content,
            provider=LLMProviderName.GROK,
            model=self.model,
            fallback_triggered=False,
            input_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
            output_tokens=completion_tokens if isinstance(completion_tokens, int) else None,
        )
