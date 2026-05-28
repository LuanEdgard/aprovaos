from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.config import settings


PRODUCT_GUARDRAILS = """
Você é a camada de IA do AprovaOS, uma plataforma de organização, priorização e automação de estudos.
Responda sempre em português brasileiro.
O AprovaOS não é curso online, não substitui escola, cursinho, professores ou corretores.
Não prometa aprovação, nota, resultado garantido ou correção oficial de redação.
Ajude com organização, priorização, resumos, flashcards, revisão ativa, repetição espaçada, análise de erros e planos realistas.
Use linguagem direta, respeitosa e de apoio. Nunca humilhe o estudante por atraso ou dificuldade.
Preserve descanso e rotina real. Não crie planos impossíveis para compensar atraso.
Se houver sofrimento intenso, oriente o estudante a procurar um adulto de confiança, família, escola ou profissional qualificado.
Use apenas os dados necessários para a resposta atual. Não peça CPF, endereço ou informações desnecessárias.
Dados enviados para o provedor de IA devem ser tratados como contexto privado da solicitação, não como conteúdo de treinamento.
"""


@dataclass
class AIResponse:
    text: str
    used_ai: bool
    error: str | None = None
    data: Any = None


class AIProvider:
    """Thin OpenAI-compatible provider with deterministic fallback support.

    The app keeps all product rules in services. This provider only sends a
    bounded prompt to a configured API and returns text or JSON. If no key is
    configured, callers receive used_ai=False and can use local fallback logic.
    """

    def __init__(self) -> None:
        self.provider = settings.ai_provider.lower().strip()
        self.api_key = settings.ai_api_key.strip()
        self.model = settings.ai_model.strip()
        self.base_url = settings.ai_base_url
        self.timeout = settings.ai_timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.model)

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> AIResponse:
        if not self.is_configured:
            return AIResponse(text="", used_ai=False, error="missing_api_key")
        if self.provider not in {"openai", "openai-compatible"}:
            return AIResponse(text="", used_ai=False, error=f"unsupported_provider:{self.provider}")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": f"{PRODUCT_GUARDRAILS}\n\n{system_prompt}".strip()},
                {"role": "user", "content": truncate_text(user_prompt, 14000)},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        return self._post_chat_completion(payload)

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.15,
        max_tokens: int = 1400,
    ) -> AIResponse:
        if not self.is_configured:
            return AIResponse(text="", used_ai=False, error="missing_api_key")

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
        response = self._post_chat_completion(payload)
        if not response.used_ai:
            return response
        parsed = parse_json(response.text)
        if parsed is None:
            return AIResponse(text=response.text, used_ai=True, error="invalid_json")
        response.data = parsed
        return response

    def _post_chat_completion(self, payload: dict[str, Any]) -> AIResponse:
        try:
            import httpx
        except ImportError:
            return AIResponse(text="", used_ai=False, error="missing_httpx")

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
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # pragma: no cover - network failures vary by provider.
            return AIResponse(text="", used_ai=False, error=str(exc))

        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return AIResponse(text="", used_ai=False, error="invalid_provider_response")

        return AIResponse(text=(text or "").strip(), used_ai=True)


def get_ai_provider() -> AIProvider:
    return AIProvider()


def truncate_text(text: str | None, limit: int = 4000) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return f"{clean[:limit].rstrip()}..."


def parse_json(text: str) -> Any | None:
    if not text:
        return None
    clean = text.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", clean, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("items", "tasks", "flashcards", "cards", "resultados"):
            if isinstance(value.get(key), list):
                return value[key]
    return []
