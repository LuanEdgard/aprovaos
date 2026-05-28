from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ChatSession
from app.routers.auth import app_context, get_current_user, login_redirect, require_api_user, templates
from app.schemas import TutorChatRequest, TutorMessageRequest
from app.services.ai_prompt_service import normalize_mode
from app.services.ai_service import AIService, AIServiceError
from app.services.tutor_memory_service import get_or_create_session, message_dict, save_message, session_dict


router = APIRouter()


@router.get("/app/tutor")
def tutor_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    return templates.TemplateResponse(request, "tutor.html", app_context(request, user, "tutor", "Tutor IA"))


@router.post("/api/tutor/message")
def tutor_message(payload: TutorMessageRequest, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    service = AIService(db, current_user.id)
    try:
        return service.chat(current_user.id, payload.message, payload.mode)
    except AIServiceError as exc:
        _raise_service_error(exc)


@router.get("/api/tutor/sessions")
def list_sessions(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    sessions = db.query(ChatSession).filter(ChatSession.user_id == current_user.id).order_by(ChatSession.updated_at.desc()).all()
    return {"sessions": [session_dict(session) for session in sessions]}


@router.post("/api/tutor/sessions")
def create_session(payload: dict, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    session = get_or_create_session(current_user.id, payload.get("mode") or "organizer", db, first_message=payload.get("title"))
    db.commit()
    db.refresh(session)
    return {"message": "Conversa criada.", "session": session_dict(session, include_messages=True)}


@router.get("/api/tutor/sessions/{session_id}/messages")
def get_session_messages(session_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"session": session_dict(session, include_messages=True)}


@router.put("/api/tutor/sessions/{session_id}")
def rename_session(session_id: int, payload: dict, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    title = " ".join(str(payload.get("title") or "").split())
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="Informe um título válido.")
    session.title = title[:180]
    db.commit()
    return {"message": "Conversa renomeada.", "session": session_dict(session)}


@router.delete("/api/tutor/sessions/{session_id}")
def delete_session(session_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    db.delete(session)
    db.commit()
    return {"message": "Conversa removida."}


@router.post("/api/tutor/chat")
def tutor_chat(payload: TutorChatRequest, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    mode = normalize_mode(payload.mode)
    session = get_or_create_session(current_user.id, mode, db, payload.session_id, payload.message)
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
        result = service.chat(current_user.id, payload.message, mode, session.id, payload.material_id)
    except AIServiceError as exc:
        _raise_service_error(exc)
    cited_ids = [
        int(item.get("id"))
        for item in (result.get("sources") or [])
        if isinstance(item, dict) and item.get("type") == "material" and str(item.get("id", "")).isdigit()
    ]
    assistant_message = save_message(
        session.id,
        "assistant",
        str(result.get("answer") or ""),
        db,
        cited_ids,
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
        "session": session_dict(session),
        "message": message_dict(assistant_message),
        "reply": result.get("answer"),
        "answer": result.get("answer"),
        "actions": result.get("actions", []),
        "warning": result.get("warning"),
        "mock_mode": result.get("mock_mode"),
        "used_context": result.get("used_context"),
        "sources": result.get("sources", []),
        "used_ai": result.get("used_ai", False),
    }


def _raise_service_error(error: AIServiceError) -> None:
    if error.code == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=error.message)
    if error.code == "FORBIDDEN":
        raise HTTPException(status_code=403, detail=error.message)
    if error.code == "VALIDATION_ERROR":
        raise HTTPException(status_code=400, detail=error.message)
    raise HTTPException(status_code=503, detail=error.message)
