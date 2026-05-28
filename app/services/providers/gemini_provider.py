from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.services.ai_provider_registry import AIProviderError, ProviderCallResult
from app.services.ai_utils import PRODUCT_GUARDRAILS, parse_json, truncate_text


class GeminiProvider:
    provider_name = "gemini"

    def __init__(self, api_key: str, model: str, *, timeout: float | None = None) -> None:
        self.api_key = api_key
        self.model = model
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
        prompt = f"{PRODUCT_GUARDRAILS}\n\n{system_prompt}\n\nSolicitação:\n{truncate_text(user_prompt, 14000)}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        text = self._post_generate_content(payload)
        return ProviderCallResult(text=text, provider_name=self.provider_name, model=self.model)

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.15,
        max_tokens: int = 1400,
    ) -> ProviderCallResult:
        response = self.generate_text(
            f"{system_prompt}\n\nResponda somente com JSON válido. Não inclua markdown.",
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        data = parse_json(response.text)
        if data is None:
            raise AIProviderError("AI_JSON_PARSE_ERROR")
        response.data = data
        return response

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

    def _post_generate_content(self, payload: dict[str, Any]) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, params={"key": self.api_key}, json=payload)
        except httpx.TimeoutException as exc:
            raise AIProviderError("AI_CONNECTION_FAILED") from exc
        except httpx.HTTPError as exc:
            raise AIProviderError("AI_CONNECTION_FAILED") from exc

        if response.status_code in {400, 401, 403}:
            raise AIProviderError("AI_KEY_INVALID")
        if response.status_code == 402:
            raise AIProviderError("AI_BILLING_REQUIRED")
        if response.status_code == 429:
            raise AIProviderError("AI_RATE_LIMITED")
        if response.status_code >= 400:
            raise AIProviderError("AI_CONNECTION_FAILED")

        try:
            data = response.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AIProviderError("AI_BAD_RESPONSE") from exc

        return (text or "").strip()
