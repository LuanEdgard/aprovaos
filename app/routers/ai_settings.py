from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import AIProviderConfig, AIRoutingConfig, AIUsageLog
from app.routers.auth import app_context, get_current_user, login_redirect, require_admin_user, require_api_user, templates, is_admin_user
from app.schemas import AIKeySaveRequest, AIProviderUpdate, AIRoutingUpdate
from app.services.ai_gateway import AIGateway
from app.services.ai_key_manager import encrypt_api_key, mask_api_key, validate_key_format
from app.services.ai_provider_registry import AI_ERROR_MESSAGES_PT, DEFAULT_ROUTING, MODULES, PROVIDERS, AIProviderError, provider_default_model


router = APIRouter()


@router.get("/app/settings/ai-integrations")
def ai_integrations_page(request: Request, db: Session = Depends(get_db)):
    _ensure_ai_settings_ui_enabled()
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    if not is_admin_user(user, db):
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores do AprovaOS.")
    return templates.TemplateResponse(
        request,
        "ai_integrations.html",
        app_context(request, user, "ai-integrations", "Integrações de IA"),
    )


@router.get("/api/settings/ai-integrations")
def get_ai_integrations(current_user=Depends(require_admin_user), db: Session = Depends(get_db)):
    _ensure_ai_settings_ui_enabled()
    return _settings_payload(db)


@router.get("/api/settings/ai-integrations/status")
def get_ai_status(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    if not settings.ai_settings_ui_enabled or not is_admin_user(current_user, db):
        return {"visible": False, "message": "Configurações de IA disponíveis apenas para administradores."}
    payload = _settings_payload(db)
    return {
        "visible": True,
        "configured": payload["overview"]["configured"],
        "active_provider": payload["overview"]["active_provider"],
        "enabled_providers": payload["overview"]["enabled_providers"],
        "last_tested_at": payload["overview"]["last_tested_at"],
        "ensemble_enabled": payload["overview"]["ensemble_enabled"],
        "key_management_mode": payload["overview"]["key_management_mode"],
    }


@router.post("/api/settings/ai-integrations/{provider}/save-key")
def save_provider_key(provider: str, payload: AIKeySaveRequest, current_user=Depends(require_admin_user), db: Session = Depends(get_db)):
    _ensure_ai_settings_ui_enabled()
    if settings.ai_internal_keys_only:
        raise HTTPException(status_code=403, detail="As chaves de IA são internas do servidor e não podem ser salvas pela interface.")
    provider = _provider_or_404(provider)
    validation = validate_key_format(provider, payload.api_key)
    if not validation.ok:
        raise HTTPException(status_code=400, detail=validation.message or AI_ERROR_MESSAGES_PT["AI_KEY_INVALID"])

    raw_key = payload.api_key.strip()
    try:
        encrypted = encrypt_api_key(raw_key)
    except AIProviderError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    config = _get_or_create_config(provider, db)
    config.encrypted_api_key = encrypted
    config.key_preview = mask_api_key(raw_key)
    config.default_model = payload.default_model or config.default_model or provider_default_model(provider)
    config.enabled = payload.enabled
    config.use_for_tutor = payload.use_for_tutor
    config.use_for_materials = payload.use_for_materials
    config.use_for_flashcards = payload.use_for_flashcards
    config.use_for_planning = payload.use_for_planning
    config.use_for_reports = payload.use_for_reports
    config.use_for_recovery = payload.use_for_recovery
    config.use_for_general = payload.use_for_general
    config.last_test_status = "not_tested"
    config.last_test_error = None
    config.created_by_user_id = current_user.id
    config.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(config)
    raw_key = ""
    return {"message": "Chave salva com criptografia.", "provider": _provider_dict(config)}


@router.post("/api/settings/ai-integrations/{provider}/test")
def test_provider(provider: str, current_user=Depends(require_admin_user), db: Session = Depends(get_db)):
    _ensure_ai_settings_ui_enabled()
    provider = _provider_or_404(provider)
    config = _get_or_create_config(provider, db)
    response = AIGateway(db, current_user.id).test_connection(provider)
    config.last_test_status = "connected" if response.used_ai else "error"
    config.last_test_error = None if response.used_ai else response.friendly_message
    config.last_tested_at = datetime.now(timezone.utc)
    if response.used_ai:
        config.last_successful_tested_at = config.last_tested_at
    db.commit()
    db.refresh(config)
    if not response.used_ai:
        return {"message": response.friendly_message, "provider": _provider_dict(config), "ok": False}
    return {"message": "Conexão testada com sucesso.", "provider": _provider_dict(config), "ok": True}


@router.patch("/api/settings/ai-integrations/routing")
def update_routing(payload: AIRoutingUpdate, current_user=Depends(require_admin_user), db: Session = Depends(get_db)):
    _ensure_ai_settings_ui_enabled()
    if settings.ai_internal_keys_only:
        raise HTTPException(status_code=403, detail="O roteamento de IA é interno e usa ensemble automático dos provedores configurados.")
    for item in payload.routes:
        route = db.query(AIRoutingConfig).filter(AIRoutingConfig.module_name == item.module_name).first()
        if not route:
            route = AIRoutingConfig(module_name=item.module_name)
            db.add(route)
        route.provider_name = item.provider_name
        route.model = item.model
        route.fallback_order = ",".join(item.fallback_order)
        route.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Roteamento de IA atualizado.", "routing": _routing_payload(db)}


@router.patch("/api/settings/ai-integrations/{provider}")
def update_provider(provider: str, payload: AIProviderUpdate, current_user=Depends(require_admin_user), db: Session = Depends(get_db)):
    _ensure_ai_settings_ui_enabled()
    if settings.ai_internal_keys_only:
        raise HTTPException(status_code=403, detail="As configurações de provedores são internas do servidor.")
    provider = _provider_or_404(provider)
    config = _get_or_create_config(provider, db)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(config, key, value)
    config.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(config)
    return {"message": "Configuração atualizada.", "provider": _provider_dict(config)}


@router.get("/api/settings/ai-integrations/usage")
def get_ai_usage(current_user=Depends(require_admin_user), db: Session = Depends(get_db)):
    _ensure_ai_settings_ui_enabled()
    logs = db.query(AIUsageLog).order_by(AIUsageLog.created_at.desc()).limit(80).all()
    return {"usage": [_usage_dict(log) for log in logs]}


def _ensure_ai_settings_ui_enabled() -> None:
    if not settings.ai_settings_ui_enabled:
        raise HTTPException(status_code=404, detail="Configurações de IA indisponíveis na interface.")


def _settings_payload(db: Session) -> dict[str, object]:
    providers = [_safe_provider_payload(name, db) for name in PROVIDERS]
    configured = [item for item in providers if item["configured"] and item["enabled"]]
    last_tested = [
        item["last_tested_at"]
        for item in providers
        if item.get("last_tested_at")
    ]
    return {
        "overview": {
            "configured": bool(configured),
            "active_provider": "ensemble" if settings.ai_ensemble_enabled and len(configured) > 1 else (configured[0]["provider_name"] if configured else None),
            "enabled_providers": [item["provider_name"] for item in configured],
            "last_tested_at": max(last_tested) if last_tested else None,
            "warning": None if configured else "Nenhuma IA foi configurada ainda.",
            "key_management_mode": "internal" if settings.ai_internal_keys_only else "admin",
            "ensemble_enabled": settings.ai_ensemble_enabled,
        },
        "providers": providers,
        "routing": _routing_payload(db),
        "modules": [{"module_name": key, "label": label} for key, label in MODULES.items()],
        "provider_options": [
            {"provider_name": key, "label": meta["label"], "models": meta["models"], "default_model": meta["default_model"]}
            for key, meta in PROVIDERS.items()
        ],
        "usage": [_usage_dict(log) for log in db.query(AIUsageLog).order_by(AIUsageLog.created_at.desc()).limit(25).all()],
    }


def _safe_provider_payload(provider_name: str, db: Session) -> dict[str, object]:
    config = db.query(AIProviderConfig).filter(AIProviderConfig.provider_name == provider_name).first()
    env_configured = bool(_env_key(provider_name))
    if not config:
        return {
            "provider_name": provider_name,
            "label": PROVIDERS[provider_name]["label"],
            "configured": env_configured,
            "source": "internal" if env_configured else "none",
            "key_preview": "chave interna configurada" if env_configured else None,
            "default_model": provider_default_model(provider_name),
            "enabled": env_configured,
            "priority": 100,
            "last_test_status": "env_configured" if env_configured else "not_configured",
            "last_test_error": None,
            "last_tested_at": None,
            "last_successful_tested_at": None,
            "models": PROVIDERS[provider_name]["models"],
            "use_for_tutor": True,
            "use_for_materials": True,
            "use_for_flashcards": True,
            "use_for_planning": True,
            "use_for_reports": True,
            "use_for_recovery": True,
            "use_for_general": True,
        }
    data = _provider_dict(config)
    data["configured"] = bool(env_configured if settings.ai_internal_keys_only else (config.encrypted_api_key or env_configured))
    data["source"] = "internal" if env_configured else ("database" if config.encrypted_api_key and not settings.ai_internal_keys_only else "none")
    data["key_preview"] = "chave interna configurada" if env_configured else (config.key_preview if not settings.ai_internal_keys_only else None)
    data["models"] = PROVIDERS[provider_name]["models"]
    return data


def _provider_dict(config: AIProviderConfig) -> dict[str, object]:
    return {
        "provider_name": config.provider_name,
        "label": PROVIDERS[config.provider_name]["label"],
        "configured": bool(config.encrypted_api_key),
        "key_preview": config.key_preview,
        "default_model": config.default_model or provider_default_model(config.provider_name),
        "enabled": config.enabled,
        "priority": config.priority,
        "use_for_tutor": config.use_for_tutor,
        "use_for_materials": config.use_for_materials,
        "use_for_flashcards": config.use_for_flashcards,
        "use_for_planning": config.use_for_planning,
        "use_for_reports": config.use_for_reports,
        "use_for_recovery": config.use_for_recovery,
        "use_for_general": config.use_for_general,
        "last_test_status": config.last_test_status,
        "last_test_error": config.last_test_error,
        "last_tested_at": config.last_tested_at.isoformat() if config.last_tested_at else None,
        "last_successful_tested_at": config.last_successful_tested_at.isoformat() if config.last_successful_tested_at else None,
    }


def _routing_payload(db: Session) -> list[dict[str, object]]:
    rows = {row.module_name: row for row in db.query(AIRoutingConfig).all()}
    data = []
    for module_name, default_order in DEFAULT_ROUTING.items():
        row = rows.get(module_name)
        provider = row.provider_name if row else default_order[0]
        fallbacks = [item.strip() for item in (row.fallback_order if row else ",".join(default_order[1:])).split(",") if item.strip()]
        data.append(
            {
                "module_name": module_name,
                "label": MODULES[module_name],
                "provider_name": provider,
                "model": row.model if row else None,
                "fallback_order": fallbacks,
            }
        )
    return data


def _usage_dict(log: AIUsageLog) -> dict[str, object]:
    return {
        "id": log.id,
        "provider_name": log.provider_name,
        "model": log.model,
        "module_name": log.module_name,
        "request_type": log.request_type,
        "success": log.success,
        "error_message": log.error_message,
        "estimated_input_tokens": log.estimated_input_tokens,
        "estimated_output_tokens": log.estimated_output_tokens,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _get_or_create_config(provider: str, db: Session) -> AIProviderConfig:
    config = db.query(AIProviderConfig).filter(AIProviderConfig.provider_name == provider).first()
    if config:
        return config
    config = AIProviderConfig(
        provider_name=provider,
        default_model=provider_default_model(provider),
        enabled=False,
    )
    db.add(config)
    db.flush()
    return config


def _provider_or_404(provider: str) -> str:
    provider = (provider or "").strip().lower()
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Provedor de IA não encontrado.")
    return provider


def _env_key(provider_name: str) -> str:
    if provider_name == "openai":
        return settings.openai_api_key.strip()
    if provider_name == "gemini":
        return settings.gemini_api_key.strip()
    if provider_name == "deepseek":
        return settings.deepseek_api_key.strip()
    return ""
