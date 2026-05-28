from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ChatSession
from app.routers.auth import require_api_user
from app.schemas import AIActionApplyRequest, AIChatRequest, AIConversationCreateRequest, AIMaterialAskRequest
from app.services.ai_prompt_service import list_modes, normalize_mode
from app.services.ai_service import AIService, AIServiceError
from app.services.tutor_memory_service import get_or_create_session, message_dict, save_message, session_dict


router = APIRouter()


@router.get("/api/ai/modes")
def get_ai_modes():
    return {"modes": list_modes()}


@router.get("/api/ai/materials")
def get_ai_materials(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    service = AIService(db, current_user.id)
    return {"materials": service.context_service.list_user_materials(current_user.id, 100)}


@router.get("/api/ai/conversations")
def list_conversations(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return {"conversations": [session_dict(session) for session in sessions]}


@router.post("/api/ai/conversations")
def create_conversation(
    payload: AIConversationCreateRequest,
    current_user=Depends(require_api_user),
    db: Session = Depends(get_db),
):
    mode = normalize_mode(payload.mode)
    session = get_or_create_session(
        current_user.id,
        mode,
        db,
        None,
        payload.title or "Nova conversa",
    )
    db.commit()
    db.refresh(session)
    return {"conversation": session_dict(session, include_messages=True)}


@router.get("/api/ai/conversations/{conversation_id}")
def get_conversation(conversation_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == conversation_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"conversation": session_dict(session, include_messages=True)}


@router.delete("/api/ai/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == conversation_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    db.delete(session)
    db.commit()
    return {"message": "Conversa removida."}


@router.post("/api/ai/chat")
def ai_chat(payload: AIChatRequest, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    mode = normalize_mode(payload.mode)
    session = get_or_create_session(
        current_user.id,
        mode,
        db,
        payload.conversation_id,
        payload.message,
    )
    save_message(
        session.id,
        "user",
        payload.message,
        db,
        metadata_json={
            "mode": mode,
            "material_id": payload.material_id,
        },
    )
    service = AIService(db, current_user.id)
    try:
        result = service.chat(
            current_user.id,
            payload.message,
            mode,
            session.id,
            payload.material_id,
        )
    except AIServiceError as exc:
        _raise_service_error(exc)

    cited_material_ids = [
        int(item.get("id"))
        for item in (result.get("sources") or [])
        if isinstance(item, dict) and item.get("type") == "material" and str(item.get("id", "")).isdigit()
    ]
    assistant_message = save_message(
        session.id,
        "assistant",
        str(result.get("answer") or ""),
        db,
        cited_material_ids=cited_material_ids,
        metadata_json={
            "mode": result.get("mode"),
            "sources": result.get("sources"),
            "actions": result.get("actions"),
            "used_context": result.get("used_context"),
            "warning": result.get("warning"),
            "mock_mode": result.get("mock_mode"),
            "provider": result.get("provider"),
            "model": result.get("model"),
            "used_ai": result.get("used_ai"),
        },
    )
    db.commit()
    db.refresh(session)
    return {
        **result,
        "conversation": session_dict(session),
        "assistant_message": message_dict(assistant_message),
    }


@router.post("/api/ai/reorganize-week")
def ai_reorganize_week(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    service = AIService(db, current_user.id)
    try:
        return service.reorganize_week(current_user.id)
    except AIServiceError as exc:
        _raise_service_error(exc)


@router.post("/api/ai/prioritize-tasks")
def ai_prioritize_tasks(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    service = AIService(db, current_user.id)
    try:
        return service.prioritize_tasks(current_user.id)
    except AIServiceError as exc:
        _raise_service_error(exc)


@router.post("/api/ai/materials/{material_id}/summarize")
def ai_summarize_material(material_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    service = AIService(db, current_user.id)
    try:
        return service.summarize_material(current_user.id, material_id)
    except AIServiceError as exc:
        _raise_service_error(exc)


@router.post("/api/ai/materials/{material_id}/ask")
def ai_ask_material(
    material_id: int,
    payload: AIMaterialAskRequest,
    current_user=Depends(require_api_user),
    db: Session = Depends(get_db),
):
    service = AIService(db, current_user.id)
    try:
        return service.ask_material(current_user.id, material_id, payload.question)
    except AIServiceError as exc:
        _raise_service_error(exc)


@router.post("/api/ai/materials/{material_id}/generate-flashcards")
def ai_generate_flashcards(material_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    service = AIService(db, current_user.id)
    try:
        return service.generate_flashcards_from_material(current_user.id, material_id)
    except AIServiceError as exc:
        _raise_service_error(exc)


@router.post("/api/ai/materials/{material_id}/generate-tasks")
def ai_generate_tasks(material_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    service = AIService(db, current_user.id)
    try:
        return service.generate_pending_tasks_from_material(current_user.id, material_id)
    except AIServiceError as exc:
        _raise_service_error(exc)


@router.post("/api/ai/reports/weekly-insights")
def ai_weekly_insights(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    service = AIService(db, current_user.id)
    try:
        return service.generate_weekly_report_insights(current_user.id)
    except AIServiceError as exc:
        _raise_service_error(exc)


@router.post("/api/ai/actions/apply")
def ai_apply_action(
    payload: AIActionApplyRequest,
    current_user=Depends(require_api_user),
    db: Session = Depends(get_db),
):
    service = AIService(db, current_user.id)
    try:
        return service.apply_action(current_user.id, payload.action, payload.payload)
    except AIServiceError as exc:
        _raise_service_error(exc)


def _raise_service_error(error: AIServiceError) -> None:
    if error.code == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=error.message)
    if error.code == "FORBIDDEN":
        raise HTTPException(status_code=403, detail=error.message)
    if error.code == "VALIDATION_ERROR":
        raise HTTPException(status_code=400, detail=error.message)
    raise HTTPException(status_code=503, detail=error.message)
