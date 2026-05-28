from __future__ import annotations

from dataclasses import dataclass


AI_ERROR_MESSAGES_PT = {
    "AI_PROVIDER_NOT_CONFIGURED": "A IA ainda não foi configurada no servidor.",
    "AI_KEY_MISSING": "Nenhuma chave de API foi configurada para este provedor.",
    "AI_KEY_INVALID": "A chave da API parece inválida.",
    "AI_PROVIDER_DISABLED": "Este provedor de IA está desativado.",
    "AI_CONNECTION_FAILED": "Não foi possível conectar ao provedor agora.",
    "AI_RATE_LIMITED": "O provedor limitou as requisições. Tente novamente em instantes.",
    "AI_BILLING_REQUIRED": "A IA do servidor está sem saldo ou quota no provedor.",
    "AI_BAD_RESPONSE": "A IA retornou uma resposta inválida. Tente novamente.",
    "AI_JSON_PARSE_ERROR": "A IA retornou uma resposta fora do formato esperado. Tente novamente.",
}


PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "default_model": "gpt-4.1-mini",
        "models": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-4o"],
    },
    "gemini": {
        "label": "Google Gemini",
        "default_model": "gemini-1.5-flash",
        "models": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"],
    },
    "deepseek": {
        "label": "DeepSeek",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
}


MODULES = {
    "tutor": "Tutor IA",
    "materials": "Materiais",
    "flashcards": "Flashcards",
    "planning": "Planejamento",
    "reports": "Relatórios",
    "recovery": "Recuperação",
    "general": "Fallback geral",
}


MODULE_PURPOSE_FIELDS = {
    "tutor": "use_for_tutor",
    "materials": "use_for_materials",
    "flashcards": "use_for_flashcards",
    "planning": "use_for_planning",
    "reports": "use_for_reports",
    "recovery": "use_for_recovery",
    "general": "use_for_general",
}


DEFAULT_ROUTING = {
    "tutor": ["openai", "gemini", "deepseek"],
    "materials": ["gemini", "openai", "deepseek"],
    "flashcards": ["openai", "gemini", "deepseek"],
    "planning": ["openai", "gemini", "deepseek"],
    "reports": ["openai", "gemini", "deepseek"],
    "recovery": ["openai", "gemini", "deepseek"],
    "general": ["openai", "gemini", "deepseek"],
}

ENSEMBLE_PROVIDER_ORDER = ["openai", "gemini", "deepseek"]


@dataclass
class ProviderCallResult:
    text: str
    provider_name: str
    model: str
    data: object | None = None


class AIProviderError(Exception):
    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message or AI_ERROR_MESSAGES_PT.get(code, "Erro de IA.")
        super().__init__(self.message)


def provider_label(provider_name: str) -> str:
    return PROVIDERS.get(provider_name, {}).get("label", provider_name)


def provider_default_model(provider_name: str) -> str:
    return PROVIDERS.get(provider_name, {}).get("default_model", "")
