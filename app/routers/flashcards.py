from datetime import datetime, timezone
from io import StringIO
import csv

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Flashcard, FlashcardDeck, FlashcardReview, Material, Subject, SubjectFront, SubjectTopic
from app.routers.auth import app_context, get_current_user, login_redirect, require_api_user, templates
from app.schemas import FlashcardCreate, FlashcardReviewRequest
from app.services.material_classifier import classify_material
from app.services.material_parser import extract_text, save_uploaded_file
from app.services.material_processor import generate_flashcards_from_material
from app.services.flashcard_engine import get_due_flashcards, get_review_interval_days, schedule_next_review


router = APIRouter()


@router.get("/app/flashcards")
def flashcards_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    return templates.TemplateResponse(request, "flashcards.html", app_context(request, user, "flashcards", "Flashcards"))


@router.get("/api/flashcards")
def list_flashcards(
    subject_id: int | None = Query(default=None),
    front_id: int | None = Query(default=None),
    topic_id: int | None = Query(default=None),
    deck_id: int | None = Query(default=None),
    tag: str | None = Query(default=None),
    due_today: bool = Query(default=False),
    current_user=Depends(require_api_user),
    db: Session = Depends(get_db),
):
    decks = db.query(FlashcardDeck).filter(FlashcardDeck.user_id == current_user.id).order_by(FlashcardDeck.created_at.desc()).all()
    deck_stats = _deck_stats(current_user.id, db)

    cards_query = db.query(Flashcard).filter(Flashcard.user_id == current_user.id)
    cards_query = _apply_card_filters(cards_query, subject_id=subject_id, front_id=front_id, topic_id=topic_id, deck_id=deck_id, tag=tag)
    if due_today:
        now = datetime.now(timezone.utc)
        cards_query = cards_query.filter(or_(Flashcard.next_review_at.is_(None), Flashcard.next_review_at <= now))

    cards = cards_query.order_by(Flashcard.created_at.desc()).limit(200).all()
    due = get_due_flashcards(current_user.id, db)

    return {
        "decks": [_deck_dict(deck, deck_stats.get(deck.id, {})) for deck in decks],
        "cards": [_card_dict(card) for card in cards],
        "due": [_card_dict(card) for card in due],
    }


@router.get("/api/flashcards/decks")
def list_decks(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    decks = db.query(FlashcardDeck).filter(FlashcardDeck.user_id == current_user.id).order_by(FlashcardDeck.created_at.desc()).all()
    stats = _deck_stats(current_user.id, db)
    return {"decks": [_deck_dict(deck, stats.get(deck.id, {})) for deck in decks]}


@router.post("/api/flashcards")
def create_flashcard(payload: FlashcardCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    subject = None
    if payload.subject_id:
        subject = db.query(Subject).filter(Subject.id == payload.subject_id, Subject.user_id == current_user.id).first()
        if not subject:
            raise HTTPException(status_code=400, detail="Matéria inválida para este usuário.")

    front = None
    if payload.front_id:
        front = db.query(SubjectFront).join(Subject, Subject.id == SubjectFront.subject_id).filter(SubjectFront.id == payload.front_id, Subject.user_id == current_user.id).first()
        if not front:
            raise HTTPException(status_code=400, detail="Frente inválida para este usuário.")

    topic = None
    if payload.topic_id:
        topic = db.query(SubjectTopic).join(Subject, Subject.id == SubjectTopic.subject_id).filter(SubjectTopic.id == payload.topic_id, Subject.user_id == current_user.id).first()
        if not topic:
            raise HTTPException(status_code=400, detail="Assunto inválido para este usuário.")

    deck = None
    if payload.deck_id:
        deck = db.query(FlashcardDeck).filter(FlashcardDeck.id == payload.deck_id, FlashcardDeck.user_id == current_user.id).first()
        if not deck:
            raise HTTPException(status_code=404, detail="Baralho não encontrado.")

    if not deck:
        title = (payload.deck_title or "Baralho geral").strip() or "Baralho geral"
        deck = db.query(FlashcardDeck).filter(FlashcardDeck.user_id == current_user.id, FlashcardDeck.title == title).first()

    if not deck:
        deck = FlashcardDeck(
            user_id=current_user.id,
            title=(payload.deck_title or "Baralho geral").strip() or "Baralho geral",
            name=(payload.deck_title or "Baralho geral").strip() or "Baralho geral",
            subject_id=payload.subject_id,
            front_id=payload.front_id,
            subject=subject.name if subject else payload.subject,
            topic=topic.name if topic else payload.topic,
            description="Baralho criado manualmente.",
            source_type="personal",
            source="personal",
        )
        db.add(deck)
        db.flush()

    card = Flashcard(
        user_id=current_user.id,
        deck_id=deck.id,
        material_id=payload.material_id,
        subject_id=payload.subject_id or deck.subject_id,
        front_id=payload.front_id or deck.front_id,
        topic_id=payload.topic_id,
        subject=subject.name if subject else deck.subject,
        topic=topic.name if topic else payload.topic,
        front=payload.front,
        back=payload.back,
        tag=payload.tag,
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return {"message": "Flashcard criado.", "card": _card_dict(card)}


@router.post("/api/flashcards/{card_id}/review")
def review_flashcard(card_id: int, payload: FlashcardReviewRequest, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    card = db.query(Flashcard).filter(Flashcard.id == card_id, Flashcard.user_id == current_user.id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Flashcard não encontrado.")

    reviewed_at = datetime.now(timezone.utc)
    next_review = schedule_next_review(payload.answer_quality)
    interval_days = get_review_interval_days(payload.answer_quality)

    card.difficulty = payload.answer_quality
    card.last_review_at = reviewed_at
    card.last_reviewed_at = reviewed_at
    card.next_review_at = next_review
    card.interval_days = interval_days
    card.review_count += 1
    card.repetitions = max(0, (card.repetitions or 0) + 1)

    ease = card.ease_factor or 2.5
    if payload.answer_quality == "Errei":
        ease -= 0.2
    elif payload.answer_quality == "Difícil":
        ease -= 0.1
    elif payload.answer_quality == "Fácil":
        ease += 0.05
    card.ease_factor = min(3.0, max(1.3, ease))

    review = FlashcardReview(
        flashcard_id=card.id,
        user_id=current_user.id,
        response=payload.answer_quality,
        reviewed_at=reviewed_at,
        next_review_at=next_review,
    )
    db.add(review)
    db.commit()
    return {"message": "Revisão registrada.", "card": _card_dict(card)}


@router.post("/api/flashcards/review")
def review_flashcard_body(payload: dict, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    card_id = int(payload.get("card_id") or 0)
    return review_flashcard(card_id, FlashcardReviewRequest(answer_quality=payload.get("answer_quality", "")), current_user, db)


@router.delete("/api/flashcards/{card_id}")
def delete_flashcard(card_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    card = db.query(Flashcard).filter(Flashcard.id == card_id, Flashcard.user_id == current_user.id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Flashcard não encontrado.")
    db.delete(card)
    db.commit()
    return {"message": "Flashcard removido."}


@router.post("/api/flashcards/upload")
def upload_flashcard_material(
    title: str = Form(...),
    source_type: str = Form("personal"),
    subject: str = Form(""),
    file: UploadFile = File(...),
    current_user=Depends(require_api_user),
    db: Session = Depends(get_db),
):
    path = save_uploaded_file(file)
    extracted = extract_text(path)
    classification = classify_material(user_id=current_user.id, title=title, text=extracted, material_type="pdf", source=source_type, subject_hint=subject, tags="flashcards", db=db)
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
        extracted_text=extracted,
        summary=classification["ai_summary"],
        ai_summary=classification["ai_summary"],
        status="processado" if extracted else "precisa revisar",
    )
    db.add(material)
    db.flush()
    created = _create_cards_from_material(material, current_user.id, db)
    db.commit()
    return {"message": "Material salvo e flashcards gerados.", "material_id": material.id, "cards": [_card_dict(card) for card in created]}


@router.post("/api/flashcards/material/{material_id}/generate")
def generate_from_existing_material(material_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    material = db.query(Material).filter(Material.id == material_id, Material.user_id == current_user.id).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material não encontrado.")
    created = _create_cards_from_material(material, current_user.id, db)
    db.commit()
    return {"message": "Flashcards gerados a partir do material.", "cards": [_card_dict(card) for card in created]}


@router.get("/api/flashcards/export.csv")
def export_flashcards_csv(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["frente", "verso", "tag"])
    cards = db.query(Flashcard).filter(Flashcard.user_id == current_user.id).order_by(Flashcard.created_at.asc()).all()
    for card in cards:
        writer.writerow([card.front, card.back, card.tag or ""])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=aprovaos-flashcards.csv"})


def _apply_card_filters(query, *, subject_id: int | None, front_id: int | None, topic_id: int | None, deck_id: int | None, tag: str | None):
    if subject_id:
        query = query.filter(Flashcard.subject_id == subject_id)
    if front_id:
        query = query.filter(Flashcard.front_id == front_id)
    if topic_id:
        query = query.filter(Flashcard.topic_id == topic_id)
    if deck_id:
        query = query.filter(Flashcard.deck_id == deck_id)
    if tag:
        query = query.filter(Flashcard.tag.ilike(f"%{tag.strip()}%"))
    return query


def _deck_stats(user_id: int, db: Session) -> dict[int, dict[str, int]]:
    now = datetime.now(timezone.utc)
    totals = dict(
        db.query(Flashcard.deck_id, func.count(Flashcard.id))
        .filter(Flashcard.user_id == user_id)
        .group_by(Flashcard.deck_id)
        .all()
    )
    due = dict(
        db.query(Flashcard.deck_id, func.count(Flashcard.id))
        .filter(Flashcard.user_id == user_id)
        .filter(or_(Flashcard.next_review_at.is_(None), Flashcard.next_review_at <= now))
        .group_by(Flashcard.deck_id)
        .all()
    )
    new_cards = dict(
        db.query(Flashcard.deck_id, func.count(Flashcard.id))
        .filter(Flashcard.user_id == user_id, Flashcard.review_count == 0)
        .group_by(Flashcard.deck_id)
        .all()
    )
    stats: dict[int, dict[str, int]] = {}
    for deck_id, total in totals.items():
        stats[deck_id] = {
            "total_cards": int(total or 0),
            "due_cards": int(due.get(deck_id, 0) or 0),
            "new_cards": int(new_cards.get(deck_id, 0) or 0),
        }
    return stats


def _create_cards_from_material(material: Material, user_id: int, db: Session) -> list[Flashcard]:
    deck = db.query(FlashcardDeck).filter(FlashcardDeck.user_id == user_id, FlashcardDeck.title == f"Material: {material.title}").first()
    if not deck:
        deck = FlashcardDeck(
            user_id=user_id,
            title=f"Material: {material.title}",
            name=f"Material: {material.title}",
            subject_id=material.subject_id,
            subject=material.subject,
            topic=material.topic,
            source_type=material.source_type,
            source=material.source,
            description="Baralho gerado a partir de material.",
        )
        db.add(deck)
        db.flush()

    created = []
    for item in generate_flashcards_from_material(material, user_id=user_id, db=db):
        card = Flashcard(
            user_id=user_id,
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
    return created


def _deck_dict(deck: FlashcardDeck, stats: dict[str, int] | None = None) -> dict[str, object]:
    stats = stats or {}
    return {
        "id": deck.id,
        "title": deck.title,
        "name": deck.name or deck.title,
        "subject_id": deck.subject_id,
        "front_id": deck.front_id,
        "subject": deck.subject,
        "topic": deck.topic,
        "source_type": deck.source_type,
        "source": deck.source or deck.source_type,
        "description": deck.description,
        "total_cards": int(stats.get("total_cards", 0) or 0),
        "due_cards": int(stats.get("due_cards", 0) or 0),
        "new_cards": int(stats.get("new_cards", 0) or 0),
    }


def _card_dict(card: Flashcard) -> dict[str, object]:
    return {
        "id": card.id,
        "deck_id": card.deck_id,
        "material_id": card.material_id,
        "subject_id": card.subject_id,
        "front_id": card.front_id,
        "topic_id": card.topic_id,
        "subject": card.subject,
        "topic": card.topic,
        "front": card.front,
        "back": card.back,
        "tag": card.tag,
        "difficulty": card.difficulty,
        "interval_days": card.interval_days,
        "ease_factor": card.ease_factor,
        "repetitions": card.repetitions,
        "next_review_at": card.next_review_at.isoformat() if card.next_review_at else None,
        "last_review_at": (card.last_reviewed_at or card.last_review_at).isoformat() if (card.last_reviewed_at or card.last_review_at) else None,
        "review_count": card.review_count,
    }
