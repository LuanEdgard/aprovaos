from datetime import datetime, timezone
import json

from sqlalchemy.orm import Session

from app.models import ChatMessage, ChatSession


def get_or_create_session(user_id: int, mode: str, db: Session, session_id: int | None = None, first_message: str | None = None) -> ChatSession:
    if session_id:
        session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user_id).first()
        if session:
            session.mode = mode or session.mode
            return session
    title = _title_from_message(first_message) if first_message else "Nova conversa"
    session = ChatSession(user_id=user_id, mode=mode, title=title)
    db.add(session)
    db.flush()
    return session


def save_message(
    session_id: int,
    role: str,
    content: str,
    db: Session,
    cited_material_ids: list[int] | None = None,
    metadata_json: dict[str, object] | None = None,
) -> ChatMessage:
    message = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        cited_material_ids=",".join(str(item) for item in cited_material_ids or []) or None,
        metadata_json=json.dumps(metadata_json, ensure_ascii=False) if metadata_json else None,
    )
    db.add(message)
    session = db.get(ChatSession, session_id)
    if session:
        session.updated_at = datetime.now(timezone.utc)
        if session.title == "Nova conversa" and role == "user":
            session.title = _title_from_message(content)
    db.flush()
    return message


def session_dict(session: ChatSession, include_messages: bool = False) -> dict[str, object]:
    data = {
        "id": session.id,
        "title": session.title,
        "mode": session.mode,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }
    if include_messages:
        data["messages"] = [message_dict(message) for message in sorted(session.messages, key=lambda item: item.created_at)]
    return data


def message_dict(message: ChatMessage) -> dict[str, object]:
    metadata = {}
    if message.metadata_json:
        try:
            metadata = json.loads(message.metadata_json)
        except json.JSONDecodeError:
            metadata = {}
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "cited_material_ids": [int(item) for item in (message.cited_material_ids or "").split(",") if item],
        "metadata": metadata,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _title_from_message(message: str | None) -> str:
    clean = " ".join((message or "").split())
    if not clean:
        return "Nova conversa"
    return clean[:54] + ("..." if len(clean) > 54 else "")
