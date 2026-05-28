from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models import AIProviderConfig, AIRoutingConfig
from app.services.ai_key_manager import decrypt_api_key
from app.services.ai_provider_registry import (
    AI_ERROR_MESSAGES_PT,
    DEFAULT_ROUTING,
    ENSEMBLE_PROVIDER_ORDER,
    MODULE_PURPOSE_FIELDS,
    PROVIDERS,
    AIProviderError,
    ProviderCallResult,
    provider_default_model,
)
from app.services.ai_usage_logger import log_ai_usage
from app.services.ai_utils import as_list, parse_json, truncate_text
from app.services.providers.deepseek_provider import DeepSeekProvider
from app.services.providers.gemini_provider import GeminiProvider
from app.services.providers.openai_provider import OpenAIProvider


@dataclass
class AIResponse:
    text: str = ""
    used_ai: bool = False
    error_code: str | None = None
    friendly_message: str | None = None
    data: Any = None
    provider_name: str | None = None
    model: str | None = None


@dataclass
class ProviderCandidate:
    provider_name: str
    api_key: str
    model: str
    source: str


class AIGateway:
    def __init__(self, db: Session, user_id: int | None = None) -> None:
        self.db = db
        self.user_id = user_id

    def test_connection(self, provider_name: str) -> AIResponse:
        provider_name = _normalize_provider(provider_name)
        try:
            candidate = self._resolve_single_provider(provider_name)
        except AIProviderError as exc:
            return self._error(exc.code, exc.message)
        if not candidate:
            return self._error("AI_KEY_MISSING")
        try:
            result = self._adapter(candidate).test_connection()
            return self._success(result, request_type="test_connection", module_name="general")
        except AIProviderError as exc:
            self._log(candidate, "general", "test_connection", False, exc.message)
            return self._error(exc.code, exc.message, provider_name=candidate.provider_name, model=candidate.model)

    def generate_text(
        self,
        module_name: str,
        request_type: str,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> AIResponse:
        return self._run(
            module_name,
            request_type,
            "generate_text",
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def generate_json(
        self,
        module_name: str,
        request_type: str,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.15,
        max_tokens: int = 1400,
    ) -> AIResponse:
        return self._run(
            module_name,
            request_type,
            "generate_json",
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def summarize_material(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> AIResponse:
        return self.generate_json("materials", "summarize_material", system_prompt, user_prompt, **kwargs)

    def classify_material(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> AIResponse:
        return self.generate_json("materials", "classify_material", system_prompt, user_prompt, **kwargs)

    def generate_flashcards(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> AIResponse:
        if settings.ai_ensemble_enabled:
            return self._run_flashcard_ensemble(system_prompt, user_prompt, **kwargs)
        return self.generate_text("flashcards", "generate_flashcards", system_prompt, user_prompt, **kwargs)

    def tutor_chat(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> AIResponse:
        return self.generate_text("tutor", "tutor_chat", system_prompt, user_prompt, **kwargs)

    def plan_week(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> AIResponse:
        return self.generate_json("planning", "plan_week", system_prompt, user_prompt, **kwargs)

    def reorganize_delayed_tasks(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> AIResponse:
        return self.generate_json("recovery", "reorganize_delayed_tasks", system_prompt, user_prompt, **kwargs)

    def _run(
        self,
        module_name: str,
        request_type: str,
        method_name: str,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> AIResponse:
        module_name = _normalize_module(module_name)
        candidates = self._resolve_candidates(module_name)
        if not candidates:
            return self._error("AI_PROVIDER_NOT_CONFIGURED")
        if settings.ai_ensemble_enabled and len(candidates) > 1:
            return self._run_ensemble(module_name, request_type, method_name, system_prompt, user_prompt, candidates, **kwargs)

        last_error: AIProviderError | None = None
        for candidate in candidates:
            try:
                adapter = self._adapter(candidate)
                method = getattr(adapter, method_name)
                result: ProviderCallResult = method(
                    system_prompt,
                    truncate_text(user_prompt, 14000),
                    **kwargs,
                )
                return self._success(result, request_type=request_type, module_name=module_name)
            except AIProviderError as exc:
                last_error = exc
                self._log(candidate, module_name, request_type, False, exc.message)
                continue

        if last_error:
            return self._error(last_error.code, last_error.message)
        return self._error("AI_PROVIDER_NOT_CONFIGURED")

    def _run_ensemble(
        self,
        module_name: str,
        request_type: str,
        method_name: str,
        system_prompt: str,
        user_prompt: str,
        candidates: list[ProviderCandidate],
        **kwargs: Any,
    ) -> AIResponse:
        successes: list[ProviderCallResult] = []
        errors: list[AIProviderError] = []
        with ThreadPoolExecutor(max_workers=min(len(candidates), 3)) as executor:
            future_map = {
                executor.submit(self._call_candidate, candidate, method_name, system_prompt, user_prompt, kwargs): candidate
                for candidate in candidates
            }
            for future in as_completed(future_map):
                candidate = future_map[future]
                try:
                    result = future.result()
                    successes.append(result)
                    self._log(
                        candidate,
                        module_name,
                        request_type,
                        True,
                        None,
                        estimated_output_tokens=_estimate_tokens(result.text),
                    )
                except AIProviderError as exc:
                    errors.append(exc)
                    self._log(candidate, module_name, request_type, False, exc.message)

        if not successes:
            last_error = errors[-1] if errors else AIProviderError("AI_PROVIDER_NOT_CONFIGURED")
            return self._error(last_error.code, last_error.message)
        if len(successes) == 1:
            result = successes[0]
            return AIResponse(text=result.text, data=result.data, used_ai=True, provider_name=result.provider_name, model=result.model)
        if method_name == "generate_json":
            return self._synthesize_json(module_name, request_type, system_prompt, user_prompt, successes, candidates, **kwargs)
        return self._synthesize_text(module_name, request_type, system_prompt, user_prompt, successes, candidates, **kwargs)

    def _call_candidate(
        self,
        candidate: ProviderCandidate,
        method_name: str,
        system_prompt: str,
        user_prompt: str,
        kwargs: dict[str, Any],
    ) -> ProviderCallResult:
        adapter = self._adapter(candidate)
        method = getattr(adapter, method_name)
        return method(system_prompt, truncate_text(user_prompt, 14000), **kwargs)

    def _synthesize_text(
        self,
        module_name: str,
        request_type: str,
        system_prompt: str,
        user_prompt: str,
        successes: list[ProviderCallResult],
        candidates: list[ProviderCandidate],
        **kwargs: Any,
    ) -> AIResponse:
        synthesis_candidate = self._pick_synthesis_candidate(candidates, successes)
        synthesis_prompt = json.dumps(
            [
                {"provider": result.provider_name, "model": result.model, "response": truncate_text(result.text, 5000)}
                for result in successes
            ],
            ensure_ascii=False,
            indent=2,
        )
        try:
            result = self._adapter(synthesis_candidate).generate_text(
                (
                    "Você é o orquestrador de IA do AprovaOS. Combine criticamente as respostas de múltiplos provedores. "
                    "Entregue uma resposta única, mais precisa, direta, em português brasileiro, sem mencionar disputa entre modelos."
                ),
                (
                    f"Pedido original do sistema:\n{system_prompt}\n\n"
                    f"Pedido do usuário/contexto:\n{truncate_text(user_prompt, 5000)}\n\n"
                    f"Respostas dos provedores:\n{synthesis_prompt}"
                ),
                temperature=kwargs.get("temperature", 0.15),
                max_tokens=kwargs.get("max_tokens", 1200),
            )
            self._log(synthesis_candidate, module_name, f"{request_type}_ensemble_synthesis", True, None)
            return AIResponse(
                text=result.text,
                used_ai=True,
                provider_name="+".join(result.provider_name for result in successes),
                model="ensemble",
            )
        except AIProviderError as exc:
            self._log(synthesis_candidate, module_name, f"{request_type}_ensemble_synthesis", False, exc.message)
            combined = "\n\n".join(
                f"Síntese parcial de {result.provider_name}:\n{truncate_text(result.text, 1800)}"
                for result in successes
            )
            return AIResponse(text=combined, used_ai=True, provider_name="+".join(result.provider_name for result in successes), model="ensemble")

    def _synthesize_json(
        self,
        module_name: str,
        request_type: str,
        system_prompt: str,
        user_prompt: str,
        successes: list[ProviderCallResult],
        candidates: list[ProviderCandidate],
        **kwargs: Any,
    ) -> AIResponse:
        parsed_items = [result.data for result in successes if result.data is not None]
        if not parsed_items:
            parsed_items = [parse_json(result.text) for result in successes]
            parsed_items = [item for item in parsed_items if item is not None]
        if not parsed_items:
            return self._error("AI_JSON_PARSE_ERROR")

        synthesis_candidate = self._pick_synthesis_candidate(candidates, successes)
        try:
            result = self._adapter(synthesis_candidate).generate_json(
                (
                    "Você é o orquestrador de IA do AprovaOS. Combine respostas JSON de múltiplos provedores. "
                    "Mantenha exatamente a intenção do schema pedido. Responda somente JSON válido."
                ),
                (
                    f"Schema/instrução original:\n{system_prompt}\n\n"
                    f"Contexto original resumido:\n{truncate_text(user_prompt, 5000)}\n\n"
                    f"JSONs dos provedores:\n{json.dumps(parsed_items, ensure_ascii=False, default=str)[:12000]}"
                ),
                temperature=kwargs.get("temperature", 0.1),
                max_tokens=kwargs.get("max_tokens", 1400),
            )
            self._log(synthesis_candidate, module_name, f"{request_type}_ensemble_synthesis", True, None)
            return AIResponse(
                text=result.text,
                data=result.data,
                used_ai=True,
                provider_name="+".join(item.provider_name for item in successes),
                model="ensemble",
            )
        except AIProviderError as exc:
            self._log(synthesis_candidate, module_name, f"{request_type}_ensemble_synthesis", False, exc.message)
            merged = _merge_json_payloads(parsed_items)
            return AIResponse(
                text=json.dumps(merged, ensure_ascii=False),
                data=merged,
                used_ai=True,
                provider_name="+".join(item.provider_name for item in successes),
                model="ensemble",
            )

    def _run_flashcard_ensemble(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> AIResponse:
        candidates = self._resolve_candidates("flashcards")
        if not candidates:
            return self._error("AI_PROVIDER_NOT_CONFIGURED")
        if len(candidates) == 1:
            result = self._run("flashcards", "generate_flashcards", "generate_text", system_prompt, user_prompt, **kwargs)
            result.data = parse_json(result.text)
            return result

        cards: list[dict[str, str]] = []
        errors: list[AIProviderError] = []
        with ThreadPoolExecutor(max_workers=min(len(candidates), 3)) as executor:
            future_map = {
                executor.submit(self._call_candidate, candidate, "generate_flashcards", system_prompt, user_prompt, kwargs): candidate
                for candidate in candidates
            }
            for future in as_completed(future_map):
                candidate = future_map[future]
                try:
                    result = future.result()
                    self._log(candidate, "flashcards", "generate_flashcards", True, None, estimated_output_tokens=_estimate_tokens(result.text))
                    cards.extend(_extract_cards(result.data if result.data is not None else parse_json(result.text)))
                except AIProviderError as exc:
                    errors.append(exc)
                    self._log(candidate, "flashcards", "generate_flashcards", False, exc.message)

        unique_cards = _dedupe_cards(cards)[:20]
        if unique_cards:
            text = json.dumps(unique_cards, ensure_ascii=False)
            return AIResponse(text=text, data=unique_cards, used_ai=True, provider_name="+".join(candidate.provider_name for candidate in candidates), model="ensemble")
        if errors:
            return self._error(errors[-1].code, errors[-1].message)
        return self._error("AI_JSON_PARSE_ERROR")

    def _pick_synthesis_candidate(self, candidates: list[ProviderCandidate], successes: list[ProviderCallResult]) -> ProviderCandidate:
        preferred = settings.ai_ensemble_synthesis_provider
        successful_names = {result.provider_name for result in successes}
        for candidate in candidates:
            if candidate.provider_name == preferred and candidate.provider_name in successful_names:
                return candidate
        for candidate in candidates:
            if candidate.provider_name in successful_names:
                return candidate
        return candidates[0]

    def _resolve_candidates(self, module_name: str) -> list[ProviderCandidate]:
        order = self._routing_order(module_name)
        candidates = []
        for provider_name in order:
            try:
                candidate = self._resolve_single_provider(provider_name, module_name)
            except AIProviderError:
                candidate = None
            if candidate:
                candidates.append(candidate)
        return candidates

    def _routing_order(self, module_name: str) -> list[str]:
        if settings.ai_ensemble_enabled:
            return [provider for provider in ENSEMBLE_PROVIDER_ORDER if provider in PROVIDERS]
        routing = self.db.query(AIRoutingConfig).filter(AIRoutingConfig.module_name == module_name).first()
        if routing:
            order = [routing.provider_name]
            for item in (routing.fallback_order or "").split(","):
                provider = item.strip().lower()
                if provider and provider not in order:
                    order.append(provider)
            return [provider for provider in order if provider in PROVIDERS]
        default = DEFAULT_ROUTING.get(module_name, DEFAULT_ROUTING["general"])
        if settings.ai_default_provider in PROVIDERS:
            ordered = [settings.ai_default_provider]
            ordered.extend(provider for provider in default if provider not in ordered)
            return ordered
        return default

    def _resolve_single_provider(self, provider_name: str, module_name: str = "general") -> ProviderCandidate | None:
        provider_name = _normalize_provider(provider_name)
        config = self.db.query(AIProviderConfig).filter(AIProviderConfig.provider_name == provider_name).first()
        runtime_config = None if settings.ai_internal_keys_only else config
        routing = self.db.query(AIRoutingConfig).filter(AIRoutingConfig.module_name == module_name).first()
        model = (
            (routing.model if routing and routing.provider_name == provider_name else None)
            or (runtime_config.default_model if runtime_config else None)
            or _env_model(provider_name)
            or provider_default_model(provider_name)
        )

        if runtime_config and runtime_config.enabled is False and runtime_config.encrypted_api_key:
            return None
        if runtime_config and module_name != "general":
            purpose_field = MODULE_PURPOSE_FIELDS.get(module_name, "use_for_general")
            if not bool(getattr(runtime_config, purpose_field, True)):
                return None
        if runtime_config and runtime_config.enabled and runtime_config.encrypted_api_key:
            return ProviderCandidate(provider_name, decrypt_api_key(runtime_config.encrypted_api_key), model, "database")

        env_key = _env_key(provider_name)
        if env_key:
            return ProviderCandidate(provider_name, env_key, model, "environment")
        return None

    def _adapter(self, candidate: ProviderCandidate):
        if candidate.provider_name == "openai":
            return OpenAIProvider(candidate.api_key, candidate.model, base_url=settings.ai_base_url)
        if candidate.provider_name == "gemini":
            return GeminiProvider(candidate.api_key, candidate.model)
        if candidate.provider_name == "deepseek":
            return DeepSeekProvider(candidate.api_key, candidate.model)
        raise AIProviderError("AI_PROVIDER_NOT_CONFIGURED")

    def _success(self, result: ProviderCallResult, *, request_type: str, module_name: str) -> AIResponse:
        self._log(
            ProviderCandidate(result.provider_name, "", result.model, "unknown"),
            module_name,
            request_type,
            True,
            None,
            estimated_input_tokens=None,
            estimated_output_tokens=_estimate_tokens(result.text),
        )
        return AIResponse(
            text=result.text,
            data=result.data,
            used_ai=True,
            provider_name=result.provider_name,
            model=result.model,
        )

    def _log(
        self,
        candidate: ProviderCandidate,
        module_name: str,
        request_type: str,
        success: bool,
        error_message: str | None,
        *,
        estimated_input_tokens: int | None = None,
        estimated_output_tokens: int | None = None,
    ) -> None:
        log_ai_usage(
            self.db,
            user_id=self.user_id,
            provider_name=candidate.provider_name,
            model=candidate.model,
            module_name=module_name,
            request_type=request_type,
            success=success,
            error_message=error_message,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
        )

    def _error(
        self,
        code: str,
        message: str | None = None,
        *,
        provider_name: str | None = None,
        model: str | None = None,
    ) -> AIResponse:
        return AIResponse(
            used_ai=False,
            error_code=code,
            friendly_message=message or AI_ERROR_MESSAGES_PT.get(code, "Erro de IA."),
            provider_name=provider_name,
            model=model,
        )


def _normalize_provider(provider_name: str) -> str:
    provider = (provider_name or "").strip().lower()
    if provider not in PROVIDERS:
        raise AIProviderError("AI_PROVIDER_NOT_CONFIGURED")
    return provider


def _normalize_module(module_name: str) -> str:
    module = (module_name or "general").strip().lower()
    return module if module in DEFAULT_ROUTING else "general"


def _env_key(provider_name: str) -> str:
    if provider_name == "openai":
        return settings.openai_api_key.strip()
    if provider_name == "gemini":
        return settings.gemini_api_key.strip()
    if provider_name == "deepseek":
        return settings.deepseek_api_key.strip()
    return ""


def _env_model(provider_name: str) -> str:
    if provider_name == settings.ai_default_provider and settings.ai_default_model:
        return settings.ai_default_model
    return provider_default_model(provider_name)


def _estimate_tokens(text: str | None) -> int | None:
    if not text:
        return None
    return max(1, len(text) // 4)


def _merge_json_payloads(items: list[Any]) -> Any:
    if all(isinstance(item, list) for item in items):
        merged = []
        seen = set()
        for item in items:
            for entry in item:
                marker = json.dumps(entry, ensure_ascii=False, sort_keys=True, default=str)
                if marker not in seen:
                    seen.add(marker)
                    merged.append(entry)
        return merged
    if all(isinstance(item, dict) for item in items):
        merged: dict[str, Any] = {}
        for item in items:
            for key, value in item.items():
                if key not in merged or merged[key] in (None, "", [], {}):
                    merged[key] = value
                elif isinstance(merged[key], list) and isinstance(value, list):
                    merged[key] = _merge_json_payloads([merged[key], value])
        return merged
    return items[0] if items else None


def _extract_cards(value: Any) -> list[dict[str, str]]:
    cards = []
    for item in as_list(value):
        if not isinstance(item, dict):
            continue
        front = truncate_text(str(item.get("front") or ""), 260)
        back = truncate_text(str(item.get("back") or ""), 700)
        if len(front) < 8 or len(back) < 3:
            continue
        cards.append(
            {
                "front": front,
                "back": back,
                "tag": truncate_text(str(item.get("tag") or ""), 255),
                "topic": truncate_text(str(item.get("topic") or "Revisão ativa"), 130),
            }
        )
    return cards


def _dedupe_cards(cards: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    unique = []
    for card in cards:
        marker = f"{card['front'].lower()}|{card['back'].lower()}"
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(card)
    return unique


def parse_gateway_json(response: AIResponse) -> Any | None:
    if response.data is not None:
        return response.data
    return parse_json(response.text)
