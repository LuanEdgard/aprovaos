from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Flashcard


REVIEW_INTERVALS = {
    "Errei": 1,
    "Difícil": 2,
    "Médio": 7,
    "Fácil": 15,
}


def get_review_interval_days(answer_quality: str) -> int:
    return REVIEW_INTERVALS.get(answer_quality, 1)


def schedule_next_review(answer_quality: str) -> datetime:
    days = get_review_interval_days(answer_quality)
    return datetime.now(timezone.utc) + timedelta(days=days)


def generate_flashcards_from_text(text: str) -> list[dict[str, str]]:
    clean_text = " ".join((text or "").split())
    if not clean_text:
        return []

    sentences = [item.strip() for item in clean_text.replace("?", ".").split(".") if len(item.strip()) > 40]
    cards: list[dict[str, str]] = []
    for index, sentence in enumerate(sentences[:8], start=1):
        fragment = sentence[:160]
        cards.append(
            {
                "topic": f"Tópico {index}",
                "front": f"Explique com suas palavras: {fragment}",
                "back": sentence,
            }
        )

    if not cards:
        cards.append(
            {
                "topic": "Ideia central",
                "front": "Qual é a ideia central deste material?",
                "back": clean_text[:400],
            }
        )
    return cards


def get_due_flashcards(user_id: int, db: Session | None = None) -> list[Flashcard]:
    owns_session = db is None
    db = db or SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        return (
            db.query(Flashcard)
            .filter(Flashcard.user_id == user_id)
            .filter((Flashcard.next_review_at == None) | (Flashcard.next_review_at <= now))  # noqa: E711
            .order_by(Flashcard.next_review_at.asc().nullsfirst(), Flashcard.created_at.asc())
            .limit(20)
            .all()
        )
    finally:
        if owns_session:
            db.close()
