from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AIUsageLog


def log_ai_usage(
    db: Session,
    *,
    user_id: int | None,
    provider_name: str,
    model: str | None,
    module_name: str,
    request_type: str,
    success: bool,
    error_message: str | None = None,
    estimated_input_tokens: int | None = None,
    estimated_output_tokens: int | None = None,
) -> None:
    safe_error = " ".join((error_message or "").split())[:400] or None
    db.add(
        AIUsageLog(
            user_id=user_id,
            provider_name=provider_name,
            model=model,
            module_name=module_name,
            request_type=request_type,
            success=success,
            error_message=safe_error,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
        )
    )
