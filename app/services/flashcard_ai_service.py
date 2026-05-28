from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Flashcard, FlashcardDeck, Material
from app.services.ai_utils import truncate_text


ALLOWED_DIFFICULTY = {"facil", "medio", "dificil"}


class FlashcardAIService:
    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id

    def sanitize_suggestions(self, payload: Any, material: Material | None = None) -> list[dict[str, str]]:
        cards: list[dict[str, str]] = []
        items = payload if isinstance(payload, list) else []
        subject_hint = material.subject if material else None
        for item in items:
            if not isinstance(item, dict):
                continue
            front = truncate_text(str(item.get("front") or ""), 260)
            back = truncate_text(str(item.get("back") or ""), 750)
            subject = truncate_text(str(item.get("subject") or subject_hint or "geral"), 120)
            difficulty = str(item.get("difficulty") or "medio").strip().lower()
            if difficulty not in ALLOWED_DIFFICULTY:
                difficulty = "medio"
            if len(front) < 8 or len(back) < 4:
                continue
            cards.append(
                {
                    "front": front,
                    "back": back,
                    "subject": subject,
                    "difficulty": difficulty,
                }
            )
        return cards[:40]

    def apply_suggestions(self, material: Material | None, cards: list[dict[str, str]]) -> list[Flashcard]:
        if not cards:
            return []
        deck_title = f"Material: {material.title}" if material else "Sugestões do Tutor IA"
        deck = (
            self.db.query(FlashcardDeck)
            .filter(FlashcardDeck.user_id == self.user_id, FlashcardDeck.title == deck_title)
            .first()
        )
        if not deck:
            deck = FlashcardDeck(
                user_id=self.user_id,
                title=deck_title,
                name=deck_title,
                subject_id=material.subject_id if material else None,
                subject=material.subject if material else None,
                topic=material.topic if material else None,
                source_type=(material.source_type if material else "personal"),
                source=(material.source if material else "personal"),
                description="Baralho criado por sugestão do Tutor IA.",
            )
            self.db.add(deck)
            self.db.flush()

        created: list[Flashcard] = []
        for item in cards:
            card = Flashcard(
                user_id=self.user_id,
                deck_id=deck.id,
                material_id=material.id if material else None,
                subject_id=material.subject_id if material else None,
                subject=item.get("subject") or (material.subject if material else None),
                topic=material.topic if material else None,
                front=item["front"],
                back=item["back"],
                difficulty=item["difficulty"],
            )
            self.db.add(card)
            self.db.flush()
            created.append(card)
        self.db.commit()
        return created
