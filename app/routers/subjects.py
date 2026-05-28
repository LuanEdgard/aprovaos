from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Flashcard, FlashcardDeck, Material, StudyTask, Subject, SubjectFront, SubjectTopic
from app.routers.auth import app_context, get_current_user, login_redirect, require_api_user, templates
from app.schemas import SubjectCreate, SubjectFrontCreate, SubjectTopicCreate
from app.services.subject_service import ensure_default_subjects, subject_dict


router = APIRouter()


@router.get("/app/subjects")
def subjects_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    return templates.TemplateResponse(request, "subjects.html", app_context(request, user, "subjects", "Matérias"))


@router.get("/app/subjects/{subject_id}")
def subject_detail_page(subject_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    subject = db.query(Subject).filter(Subject.id == subject_id, Subject.user_id == user.id).first()
    if not subject:
        return login_redirect()
    return templates.TemplateResponse(request, "subject_detail.html", app_context(request, user, "subjects", subject.name, subject_id=subject.id))


@router.get("/api/subjects")
def list_subjects(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    ensure_default_subjects(current_user.id, db)
    subjects = db.query(Subject).filter(Subject.user_id == current_user.id).order_by(Subject.area.asc(), Subject.name.asc()).all()
    return {"subjects": [_subject_summary(subject, db) for subject in subjects]}


@router.post("/api/subjects")
def create_subject(payload: SubjectCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    subject = Subject(user_id=current_user.id, **payload.model_dump())
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return {"message": "Matéria criada.", "subject": _subject_summary(subject, db)}


@router.get("/api/subjects/{subject_id}")
def get_subject(subject_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    subject = _get_subject(subject_id, current_user.id, db)
    materials = db.query(Material).filter(Material.user_id == current_user.id, Material.subject_id == subject.id).order_by(Material.created_at.desc()).all()
    tasks = db.query(StudyTask).filter(StudyTask.user_id == current_user.id, StudyTask.subject_id == subject.id).order_by(StudyTask.deadline.asc().nulls_last()).all()
    decks = db.query(FlashcardDeck).filter(FlashcardDeck.user_id == current_user.id, FlashcardDeck.subject_id == subject.id).all()
    cards = db.query(Flashcard).filter(Flashcard.user_id == current_user.id, Flashcard.subject_id == subject.id).all()

    data = subject_dict(subject)
    data.update(
        {
            "fronts": [_front_item(front) for front in sorted(subject.fronts, key=lambda item: item.order)],
            "topics": [_topic_item(topic) for topic in sorted(subject.topics, key=lambda item: (item.front_id or 0, item.order))],
            "materials": [_material_item(material) for material in materials],
            "tasks": [_task_item(task) for task in tasks],
            "decks": [_deck_item(deck) for deck in decks],
            "flashcards_count": len(cards),
            "progress": _subject_progress(subject, tasks, cards),
            "ai_insight": _subject_insight(subject, tasks, cards),
        }
    )
    return {"subject": data}


@router.put("/api/subjects/{subject_id}")
def update_subject(subject_id: int, payload: SubjectCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    subject = _get_subject(subject_id, current_user.id, db)
    for key, value in payload.model_dump().items():
        setattr(subject, key, value)
    db.commit()
    return {"message": "Matéria atualizada.", "subject": _subject_summary(subject, db)}


@router.post("/api/subjects/{subject_id}/fronts")
def create_front(subject_id: int, payload: SubjectFrontCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    _get_subject(subject_id, current_user.id, db)
    front = SubjectFront(subject_id=subject_id, **payload.model_dump())
    db.add(front)
    db.commit()
    db.refresh(front)
    return {"message": "Frente criada.", "front": _front_item(front)}


@router.put("/api/subjects/{subject_id}/fronts/{front_id}")
def update_front(subject_id: int, front_id: int, payload: SubjectFrontCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    _get_subject(subject_id, current_user.id, db)
    front = (
        db.query(SubjectFront)
        .join(Subject, Subject.id == SubjectFront.subject_id)
        .filter(SubjectFront.id == front_id, SubjectFront.subject_id == subject_id, Subject.user_id == current_user.id)
        .first()
    )
    if not front:
        raise HTTPException(status_code=404, detail="Frente não encontrada.")
    for key, value in payload.model_dump().items():
        setattr(front, key, value)
    db.commit()
    return {"message": "Frente atualizada.", "front": _front_item(front)}


@router.delete("/api/subjects/{subject_id}/fronts/{front_id}")
def delete_front(subject_id: int, front_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    _get_subject(subject_id, current_user.id, db)
    front = (
        db.query(SubjectFront)
        .join(Subject, Subject.id == SubjectFront.subject_id)
        .filter(SubjectFront.id == front_id, SubjectFront.subject_id == subject_id, Subject.user_id == current_user.id)
        .first()
    )
    if not front:
        raise HTTPException(status_code=404, detail="Frente não encontrada.")
    db.delete(front)
    db.commit()
    return {"message": "Frente removida."}


@router.post("/api/subjects/{subject_id}/topics")
def create_topic(subject_id: int, payload: SubjectTopicCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    _get_subject(subject_id, current_user.id, db)
    topic = SubjectTopic(subject_id=subject_id, **payload.model_dump())
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return {"message": "Assunto criado.", "topic": _topic_item(topic)}


@router.put("/api/subjects/{subject_id}/topics/{topic_id}")
def update_topic(subject_id: int, topic_id: int, payload: SubjectTopicCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    _get_subject(subject_id, current_user.id, db)
    topic = (
        db.query(SubjectTopic)
        .join(Subject, Subject.id == SubjectTopic.subject_id)
        .filter(SubjectTopic.id == topic_id, SubjectTopic.subject_id == subject_id, Subject.user_id == current_user.id)
        .first()
    )
    if not topic:
        raise HTTPException(status_code=404, detail="Assunto não encontrado.")
    for key, value in payload.model_dump().items():
        setattr(topic, key, value)
    db.commit()
    return {"message": "Assunto atualizado.", "topic": _topic_item(topic)}


@router.delete("/api/subjects/{subject_id}/topics/{topic_id}")
def delete_topic(subject_id: int, topic_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    _get_subject(subject_id, current_user.id, db)
    topic = (
        db.query(SubjectTopic)
        .join(Subject, Subject.id == SubjectTopic.subject_id)
        .filter(SubjectTopic.id == topic_id, SubjectTopic.subject_id == subject_id, Subject.user_id == current_user.id)
        .first()
    )
    if not topic:
        raise HTTPException(status_code=404, detail="Assunto não encontrado.")
    db.delete(topic)
    db.commit()
    return {"message": "Assunto removido."}


def _get_subject(subject_id: int, user_id: int, db: Session) -> Subject:
    subject = db.query(Subject).filter(Subject.id == subject_id, Subject.user_id == user_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Matéria não encontrada.")
    return subject


def _subject_summary(subject: Subject, db: Session) -> dict[str, object]:
    data = subject_dict(subject)
    data["material_count"] = db.query(Material).filter(Material.user_id == subject.user_id, Material.subject_id == subject.id).count()
    data["task_count"] = db.query(StudyTask).filter(StudyTask.user_id == subject.user_id, StudyTask.subject_id == subject.id).count()
    data["deck_count"] = db.query(FlashcardDeck).filter(FlashcardDeck.user_id == subject.user_id, FlashcardDeck.subject_id == subject.id).count()
    return data


def _front_item(front: SubjectFront) -> dict[str, object]:
    return {
        "id": front.id,
        "name": front.name,
        "description": front.description,
        "order": front.order,
        "topic_count": len(front.topics),
    }


def _topic_item(topic: SubjectTopic) -> dict[str, object]:
    return {
        "id": topic.id,
        "name": topic.name,
        "description": topic.description,
        "order": topic.order,
        "front_id": topic.front_id,
        "status": topic.status,
        "difficulty": topic.difficulty,
    }


def _material_item(material: Material) -> dict[str, object]:
    return {
        "id": material.id,
        "title": material.title,
        "topic": material.topic,
        "subtopic": material.subtopic,
        "source": material.source or material.source_type,
        "tags": material.tags,
        "created_at": material.created_at.isoformat() if material.created_at else None,
    }


def _task_item(task: StudyTask) -> dict[str, object]:
    return {
        "id": task.id,
        "title": task.title,
        "category": task.task_category,
        "status": task.status,
        "priority": task.priority,
        "front": task.front_ref.name if task.front_ref else None,
        "topic": task.topic_ref.name if task.topic_ref else None,
        "due_date": (task.due_date or task.deadline).isoformat() if (task.due_date or task.deadline) else None,
    }


def _deck_item(deck: FlashcardDeck) -> dict[str, object]:
    return {
        "id": deck.id,
        "title": deck.title,
        "name": deck.name or deck.title,
        "topic": deck.topic,
        "front_id": deck.front_id,
    }


def _subject_progress(subject: Subject, tasks: list[StudyTask], cards: list[Flashcard]) -> dict[str, object]:
    total_topics = len(subject.topics)
    completed_topics = sum(1 for topic in subject.topics if topic.status == "concluido")
    topic_progress = round((completed_topics / total_topics) * 100, 1) if total_topics else 0

    total_tasks = len(tasks)
    completed_tasks = sum(1 for task in tasks if task.status in {"completed", "concluída"})
    task_progress = round((completed_tasks / total_tasks) * 100, 1) if total_tasks else 0

    return {
        "total_topics": total_topics,
        "completed_topics": completed_topics,
        "topic_progress": topic_progress,
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "task_progress": task_progress,
        "flashcards": len(cards),
    }


def _subject_insight(subject: Subject, tasks: list[StudyTask], cards: list[Flashcard]) -> str:
    overdue_by_front: dict[int, int] = {}
    for task in tasks:
        if task.status not in {"late", "atrasada"}:
            continue
        front_id = task.front_id or 0
        overdue_by_front[front_id] = overdue_by_front.get(front_id, 0) + 1

    if overdue_by_front:
        main_front_id = max(overdue_by_front, key=lambda item: overdue_by_front[item])
        if main_front_id:
            front = next((front for front in subject.fronts if front.id == main_front_id), None)
            if front:
                return f"Há muitas pendências atrasadas em {front.name}. Priorize recuperação dessa frente nos próximos blocos."

    due_cards = [card for card in cards if card.next_review_at is None or card.next_review_at <= datetime.now(timezone.utc)]
    if len(due_cards) >= 5:
        return "Existem muitos flashcards vencidos. Faça uma sessão curta de revisão ativa antes de novos conteúdos."

    hard_topics = [topic for topic in subject.topics if topic.difficulty == "alta"]
    if hard_topics:
        return f"Assuntos com dificuldade alta detectados ({hard_topics[0].name}). Reforce base teórica + questões fáceis de recuperação."

    return f"{subject.name} está equilibrada. Mantenha ciclo de teoria curta, prática e revisão espaçada."
