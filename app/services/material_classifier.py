from typing import Any

from sqlalchemy.orm import Session

from app.models import Subject
from app.services.ai_gateway import AIGateway
from app.services.ai_utils import truncate_text
from app.services.material_processor import detect_subject_from_text
from app.services.normalization import normalize_material_type, normalize_source
from app.services.subject_service import find_or_create_subject


def classify_material(
    *,
    user_id: int,
    title: str,
    text: str,
    material_type: str,
    source: str,
    subject_hint: str | None,
    tags: str | None,
    db: Session,
) -> dict[str, Any]:
    if text.strip():
        response = AIGateway(db, user_id).classify_material(
            "Classifique material de estudo para organização no AprovaOS. "
            "Retorne somente JSON com subject, topic, subtopic, source, tags, summary. "
            "Use português brasileiro nos nomes de matéria/tópico e slugs em inglês para source quando possível.",
            f"Título: {title}\nTipo: {material_type}\nFonte informada: {source}\nEtiquetas: {tags or ''}\nTexto:\n{truncate_text(text, 7000)}",
            max_tokens=1000,
        )
        if response.used_ai and isinstance(response.data, dict):
            data = response.data
            subject_name = str(data.get("subject") or subject_hint or detect_subject_from_text(text)).strip()
            subject = find_or_create_subject(user_id, subject_name, db, source_type=normalize_source(source))
            return {
                "subject_id": subject.id if subject else None,
                "subject": subject.name if subject else subject_name,
                "topic": str(data.get("topic") or "").strip()[:140] or None,
                "subtopic": str(data.get("subtopic") or "").strip()[:140] or None,
                "source": normalize_source(str(data.get("source") or source)),
                "type": normalize_material_type(material_type),
                "tags": _tags_to_string(data.get("tags")) or tags,
                "ai_summary": str(data.get("summary") or "").strip()[:2200] or None,
                "ai_detected_subject": subject_name[:120],
                "ai_detected_topic": str(data.get("topic") or "").strip()[:140] or None,
                "ai_detected_subtopic": str(data.get("subtopic") or "").strip()[:140] or None,
                "ai_status": "classificado por IA",
            }

    subject_name = subject_hint or detect_subject_from_text(text) or "geral"
    subject = find_or_create_subject(user_id, subject_name, db, source_type=normalize_source(source))
    return {
        "subject_id": subject.id if subject else None,
        "subject": subject.name if subject else subject_name,
        "topic": _guess_topic(text, title),
        "subtopic": None,
        "source": normalize_source(source),
        "type": normalize_material_type(material_type),
        "tags": tags,
        "ai_summary": "IA não configurada. Classificação básica feita por palavras-chave.",
        "ai_detected_subject": subject_name,
        "ai_detected_topic": _guess_topic(text, title),
        "ai_detected_subtopic": None,
        "ai_status": "IA não configurada",
    }


def _guess_topic(text: str, title: str) -> str | None:
    lower = f"{title} {text}".lower()
    hints = [
        "ecologia",
        "funções",
        "função",
        "química orgânica",
        "geometria",
        "redação",
        "literatura",
        "história do brasil",
        "mecânica",
    ]
    for hint in hints:
        if hint in lower:
            return hint.capitalize()
    return None


def _tags_to_string(value: Any) -> str | None:
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())[:255]
    if isinstance(value, str):
        return value[:255]
    return None
