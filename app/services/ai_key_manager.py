from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Any

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover - depends on local environment.
    Fernet = None  # type: ignore[assignment]

    class InvalidToken(Exception):
        pass

from app.config import settings
from app.services.ai_provider_registry import AIProviderError


@dataclass
class KeyValidationResult:
    ok: bool
    message: str | None = None


def _fernet_from_secret() -> Any:
    if Fernet is None:
        raise AIProviderError(
            "AI_KEY_MISSING",
            "A dependência cryptography não está instalada. Rode pip install -r requirements.txt.",
        )
    secret = settings.ai_keys_master_secret.strip()
    if not secret:
        raise AIProviderError(
            "AI_KEY_MISSING",
            "Configure AI_KEYS_MASTER_SECRET no .env antes de salvar chaves de IA.",
        )
    try:
        return Fernet(secret.encode("utf-8"))
    except ValueError:
        derived = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        return Fernet(derived)


def encrypt_api_key(raw_key: str) -> str:
    key = (raw_key or "").strip()
    if not key:
        raise AIProviderError("AI_KEY_MISSING")
    return _fernet_from_secret().encrypt(key.encode("utf-8")).decode("utf-8")


def decrypt_api_key(encrypted_key: str | None) -> str:
    if not encrypted_key:
        raise AIProviderError("AI_KEY_MISSING")
    try:
        return _fernet_from_secret().decrypt(encrypted_key.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise AIProviderError("AI_KEY_INVALID", "Não foi possível descriptografar a chave salva.") from exc


def mask_api_key(raw_key: str) -> str:
    key = (raw_key or "").strip()
    if not key:
        return ""
    prefix = key[:3] if len(key) > 8 else key[:2]
    suffix = key[-4:] if len(key) > 4 else ""
    return f"{prefix}••••••••••••{suffix}"


def validate_key_format(provider_name: str, raw_key: str) -> KeyValidationResult:
    key = (raw_key or "").strip()
    if len(key) < 8:
        return KeyValidationResult(False, "A chave informada é curta demais.")
    if provider_name == "openai" and not key.startswith("sk-"):
        return KeyValidationResult(False, "Chaves OpenAI normalmente começam com sk-.")
    if provider_name == "deepseek" and not key.startswith("sk-"):
        return KeyValidationResult(False, "Chaves DeepSeek normalmente começam com sk-.")
    if provider_name == "gemini" and len(key) < 20:
        return KeyValidationResult(False, "A chave Gemini parece curta demais.")
    return KeyValidationResult(True)
