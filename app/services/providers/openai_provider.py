from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.services.ai_provider_registry import AIProviderError, ProviderCallResult
from app.services.ai_utils import PRODUCT_GUARDRAILS, parse_json, truncate_text


class OpenAIProvider:
    provider_name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = "https://api.openai.com/v1",
        timeout: float | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout or settings.ai_timeout_seconds

    def test_connection(self) -> ProviderCallResult:
        return self.generate_text(
            "Você está testando uma conexão de IA. Responda apenas com OK.",
            "Teste de conexão do AprovaOS.",
            max_tokens=8,
        )

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> ProviderCallResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": f"{PRODUCT_GUARDRAILS}\n\n{system_prompt}".strip()},
                {"role": "user", "content": truncate_text(user_prompt, 14000)},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        text = self._post_chat_completion(payload)
        return ProviderCallResult(text=text, provider_name=self.provider_name, model=self.model)

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.15,
        max_tokens: int = 1400,
    ) -> ProviderCallResult:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{PRODUCT_GUARDRAILS}\n\n{system_prompt}\n\n"
                        "Responda somente com JSON válido. Não inclua markdown."
                    ).strip(),
                },
                {"role": "user", "content": truncate_text(user_prompt, 14000)},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        text = self._post_chat_completion(payload)
        data = parse_json(text)
        if data is None:
            raise AIProviderError("AI_JSON_PARSE_ERROR")
        return ProviderCallResult(text=text, data=data, provider_name=self.provider_name, model=self.model)

    def summarize_material(self, *args: Any, **kwargs: Any) -> ProviderCallResult:
        return self.generate_json(*args, **kwargs)

    def classify_material(self, *args: Any, **kwargs: Any) -> ProviderCallResult:
        return self.generate_json(*args, **kwargs)

    def generate_flashcards(self, *args: Any, **kwargs: Any) -> ProviderCallResult:
        return self.generate_text(*args, **kwargs)

    def tutor_chat(self, *args: Any, **kwargs: Any) -> ProviderCallResult:
        return self.generate_text(*args, **kwargs)

    def plan_week(self, *args: Any, **kwargs: Any) -> ProviderCallResult:
        return self.generate_json(*args, **kwargs)

    def reorganize_delayed_tasks(self, *args: Any, **kwargs: Any) -> ProviderCallResult:
        return self.generate_json(*args, **kwargs)

    def _post_chat_completion(self, payload: dict[str, Any]) -> str:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise AIProviderError("AI_CONNECTION_FAILED") from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("AI_CONNECTION_FAILED") from exc

        provider_error_code = _provider_error_code(response)
        if response.status_code in {401, 403}:
            raise AIProviderError("AI_KEY_INVALID")
        if response.status_code == 402 or provider_error_code in {"insufficient_quota", "billing_not_active"}:
            raise AIProviderError("AI_BILLING_REQUIRED")
        if response.status_code == 429:
            raise AIProviderError("AI_RATE_LIMITED")
        if response.status_code >= 400:
            raise AIProviderError("AI_CONNECTION_FAILED")

        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError("AI_BAD_RESPONSE") from exc

        return (text or "").strip()


def _provider_error_code(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if not isinstance(error, dict):
        return ""
    return str(error.get("code") or error.get("type") or "").strip()
