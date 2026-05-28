from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Flashcard, FlashcardDeck, Material, StudyTask
from app.routers.auth import app_context, get_current_user, login_redirect, require_api_user, templates
from app.schemas import MATERIAL_TYPE_MAP, TASK_SOURCE_MAP, MaterialTextCreate, _coerce
from app.services.material_classifier import classify_material
from app.services.material_parser import extract_text, save_uploaded_file
from app.services.material_processor import (
    detect_subject_from_text,
    generate_flashcards_from_material,
    generate_tasks_from_material,
    summarize_text,
)
from app.services.normalization import normalize_material_type, normalize_source
from app.services.retrieval_service import search_materials
from app.services.tutor_engine import answer_with_sources


router = APIRouter()


@router.get("/app/materials")
def materials_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    return templates.TemplateResponse(request, "materials.html", app_context(request, user, "materials", "Materiais"))


@router.get("/app/materials/{material_id}")
def material_detail_page(material_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    material = db.query(Material).filter(Material.id == material_id, Material.user_id == user.id).first()
    if not material:
        return login_redirect()
    return templates.TemplateResponse(request, "material_detail.html", app_context(request, user, "materials", material.title, material_id=material.id))


@router.get("/api/materials")
def list_materials(q: str = "", current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    materials = search_materials(current_user.id, q, db) if q else db.query(Material).filter(Material.user_id == current_user.id).order_by(Material.created_at.desc()).all()
    return {"materials": [_material_dict(material) for material in materials]}


@router.get("/api/materials/{material_id}")
def get_material(material_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    material = _get_material(material_id, current_user.id, db)
    return {"material": _material_dict(material, full=True)}


@router.post("/api/materials/{material_id}/ask")
def ask_material(material_id: int, payload: dict, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    material = _get_material(material_id, current_user.id, db)
    question = str(payload.get("question") or "").strip()
    if len(question) < 2:
        raise HTTPException(status_code=400, detail="Informe uma pergunta sobre o material.")
    return answer_with_sources(current_user.id, f"{question}\nMaterial prioritário: {material.title}", db)


@router.post("/api/materials/upload")
def upload_material(
    title: str = Form(...),
    material_type: str = Form("PDF"),
    source_type: str = Form("pessoal"),
    subject: str = Form(""),
    tags: str = Form(""),
    file: UploadFile = File(...),
    current_user=Depends(require_api_user),
    db: Session = Depends(get_db),
):
    title = title.strip()
    if len(title) < 2 or len(title) > 180:
        raise HTTPException(status_code=400, detail="Informe um título de material válido.")
    try:
        material_type = _coerce(material_type, MATERIAL_TYPE_MAP, "Tipo de material inválido.")
        source_type = _coerce(source_type, TASK_SOURCE_MAP, "Fonte do material inválida.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not material_type:
        raise HTTPException(status_code=400, detail="Tipo de material inválido.")
    if not source_type:
        raise HTTPException(status_code=400, detail="Fonte do material inválida.")
    path = save_uploaded_file(file)
    extracted_text = extract_text(path)
    classification = classify_material(
        user_id=current_user.id,
        title=title,
        text=extracted_text,
        material_type=material_type,
        source=source_type,
        subject_hint=subject or None,
        tags=tags,
        db=db,
    )
    material = Material(
        user_id=current_user.id,
        title=title,
        material_type=classification["type"],
        type=classification["type"],
        source_type=classification["source"],
        source=classification["source"],
        subject_id=classification["subject_id"],
        subject=classification["subject"],
        topic=classification["topic"],
        subtopic=classification["subtopic"],
        tags=classification["tags"],
        file_path=str(path),
        extracted_text=extracted_text,
        summary=classification["ai_summary"],
        ai_summary=classification["ai_summary"],
        ai_detected_subject=classification["ai_detected_subject"],
        ai_detected_topic=classification["ai_detected_topic"],
        ai_detected_subtopic=classification["ai_detected_subtopic"],
        status="processado" if extracted_text else "precisa revisar",
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return {"message": "Material enviado.", "material": _material_dict(material)}


@router.post("/api/materials/text")
def create_text_material(payload: MaterialTextCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    classification = classify_material(
        user_id=current_user.id,
        title=payload.title,
        text=payload.text,
        material_type=payload.material_type,
        source=payload.source_type,
        subject_hint=payload.subject,
        tags=payload.tags,
        db=db,
    )
    material = Material(
        user_id=current_user.id,
        title=payload.title,
        material_type=classification["type"],
        type=classification["type"],
        source_type=classification["source"],
        source=classification["source"],
        subject_id=payload.subject_id or classification["subject_id"],
        subject=classification["subject"],
        topic=payload.topic or classification["topic"],
        subtopic=payload.subtopic or classification["subtopic"],
        tags=classification["tags"],
        extracted_text=payload.text,
        summary=classification["ai_summary"],
        ai_summary=classification["ai_summary"],
        ai_detected_subject=classification["ai_detected_subject"],
        ai_detected_topic=classification["ai_detected_topic"],
        ai_detected_subtopic=classification["ai_detected_subtopic"],
        status="processado",
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return {"message": "Texto registrado como material.", "material": _material_dict(material)}


@router.post("/api/materials/{material_id}/summarize")
def summarize_material(material_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    material = _get_material(material_id, current_user.id, db)
    material.summary = summarize_text(material.extracted_text or "", material.title, material.subject, user_id=current_user.id, db=db)
    material.ai_summary = material.summary
    material.status = "processado" if material.extracted_text else "precisa revisar"
    db.commit()
    return {"message": "Resumo gerado.", "summary": material.summary, "material": _material_dict(material)}


@router.post("/api/materials/{material_id}/generate-tasks")
def generate_material_tasks(material_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    material = _get_material(material_id, current_user.id, db)
    created = []
    for item in generate_tasks_from_material(material, user_id=current_user.id, db=db):
        item["subject_id"] = material.subject_id
        item["source"] = item.get("source") or item.get("source_type") or material.source
        item["source_type"] = item.get("source_type") or item.get("source") or material.source_type
        item["description"] = item.get("description") or f"Pendência criada a partir do material {material.title}."
        item["task_category"] = item.get("task_category") or "material_review"
        item["subtopic"] = item.get("subtopic") or material.subtopic
        task = StudyTask(user_id=current_user.id, **item)
        db.add(task)
        db.flush()
        created.append(task)
    db.commit()
    return {"message": "Pendências sugeridas foram criadas.", "tasks": [_task_dict(task) for task in created]}


@router.post("/api/materials/{material_id}/generate-flashcards")
def generate_material_flashcards(material_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    material = _get_material(material_id, current_user.id, db)
    deck = (
        db.query(FlashcardDeck)
        .filter(FlashcardDeck.user_id == current_user.id, FlashcardDeck.title == f"Material: {material.title}")
        .first()
    )
    if not deck:
        deck = FlashcardDeck(user_id=current_user.id, title=f"Material: {material.title}", name=f"Material: {material.title}", subject_id=material.subject_id, subject=material.subject, topic=material.topic, source_type=material.source_type, source=material.source)
        db.add(deck)
        db.flush()
    created = []
    for item in generate_flashcards_from_material(material, user_id=current_user.id, db=db):
        card = Flashcard(
            user_id=current_user.id,
            deck_id=deck.id,
            material_id=material.id,
            subject_id=material.subject_id,
            subject=material.subject,
            topic=item.get("topic") or material.topic,
            front=item["front"],
            back=item["back"],
            tag=item.get("tag"),
        )
        db.add(card)
        db.flush()
        created.append(card)
    db.commit()
    return {"message": "Flashcards sugeridos foram criados.", "cards": [_card_dict(card) for card in created]}


def _get_material(material_id: int, user_id: int, db: Session) -> Material:
    material = db.query(Material).filter(Material.id == material_id, Material.user_id == user_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material não encontrado.")
    return material


def _material_dict(material: Material, full: bool = False) -> dict[str, object]:
    data = {
        "id": material.id,
        "title": material.title,
        "material_type": material.material_type,
        "type": material.type or material.material_type,
        "source_type": material.source_type,
        "source": material.source or material.source_type,
        "subject_id": material.subject_id,
        "subject": material.subject,
        "topic": material.topic,
        "subtopic": material.subtopic,
        "tags": material.tags,
        "status": material.status,
        "summary": material.ai_summary or material.summary,
        "ai_summary": material.ai_summary,
        "ai_detected_subject": material.ai_detected_subject,
        "ai_detected_topic": material.ai_detected_topic,
        "ai_detected_subtopic": material.ai_detected_subtopic,
        "extracted_text": (material.extracted_text or "") if full else (material.extracted_text or "")[:1000],
        "created_at": material.created_at.isoformat() if material.created_at else None,
    }
    return data


def _task_dict(task: StudyTask) -> dict[str, object]:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "task_category": task.task_category,
        "source": task.source or task.source_type,
        "subject_id": task.subject_id,
        "subject": task.subject,
        "source_type": task.source_type,
        "priority": task.priority,
        "status": task.status,
        "deadline": (task.due_date or task.deadline).isoformat() if (task.due_date or task.deadline) else None,
        "due_date": (task.due_date or task.deadline).isoformat() if (task.due_date or task.deadline) else None,
        "estimated_minutes": task.estimated_minutes,
    }


def _card_dict(card: Flashcard) -> dict[str, object]:
    return {"id": card.id, "front": card.front, "back": card.back, "tag": card.tag, "subject_id": card.subject_id, "subject": card.subject, "topic": card.topic}
