from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.models import Material, StudyTask
from app.services.ai_utils import truncate_text


class MaterialAIService:
    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id

    def material_source(self, material: Material) -> dict[str, Any]:
        return {
            "id": material.id,
            "title": material.title,
            "type": material.type or material.material_type,
            "subject": material.subject or (material.subject_ref.name if material.subject_ref else None),
            "topic": material.topic,
            "subtopic": material.subtopic,
            "summary": material.ai_summary or material.summary,
        }

    def content_for_prompt(self, material: Material, limit: int = 9000) -> str:
        return truncate_text(material.extracted_text or material.ai_summary or material.summary or material.title, limit)

    def sanitize_task_suggestions(self, payload: Any, material: Material | None = None) -> list[dict[str, Any]]:
        items = payload if isinstance(payload, list) else []
        suggestions: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = truncate_text(str(item.get("title") or ""), 180)
            if len(title) < 4:
                continue
            description = truncate_text(str(item.get("description") or ""), 400)
            priority = str(item.get("priority") or "média").strip().lower()
            if priority not in {"baixa", "média", "alta", "urgente"}:
                priority = "média"
            source_type = str(item.get("source_type") or (material.source_type if material else "personal")).strip().lower()
            if source_type not in {"school", "course", "vestibular", "personal", "technical_course", "other"}:
                source_type = "personal"
            try:
                estimated_minutes = int(item.get("estimated_minutes") or 40)
            except (TypeError, ValueError):
                estimated_minutes = 40
            estimated_minutes = max(15, min(estimated_minutes, 180))
            try:
                due_in_days = int(item.get("due_in_days") or item.get("days_from_now") or 3)
            except (TypeError, ValueError):
                due_in_days = 3
            due_in_days = max(0, min(due_in_days, 21))
            suggestions.append(
                {
                    "title": title,
                    "description": description or f"Sugestão do Tutor IA baseada no material {material.title if material else 'selecionado'}.",
                    "priority": priority,
                    "source_type": source_type,
                    "estimated_minutes": estimated_minutes,
                    "due_in_days": due_in_days,
                    "subject": truncate_text(
                        str(item.get("subject") or (material.subject if material else "geral")),
                        100,
                    ),
                    "task_category": str(item.get("task_category") or "material_review"),
                }
            )
        return suggestions[:40]

    def apply_task_suggestions(self, material: Material | None, suggestions: list[dict[str, Any]]) -> list[StudyTask]:
        if not suggestions:
            return []
        created: list[StudyTask] = []
        today = date.today()
        for item in suggestions:
            due_date = today + timedelta(days=int(item.get("due_in_days") or 0))
            task = StudyTask(
                user_id=self.user_id,
                material_id=material.id if material else None,
                title=item["title"],
                description=item["description"],
                task_category=item.get("task_category") or "material_review",
                source=item.get("source_type") or (material.source if material else "personal"),
                origin="ai_tutor",
                subject_id=material.subject_id if material else None,
                subject=item.get("subject") or (material.subject if material else None),
                subtopic=material.subtopic if material else None,
                source_type=item.get("source_type") or (material.source_type if material else "personal"),
                priority=item.get("priority") or "média",
                status="pending",
                deadline=due_date,
                due_date=due_date,
                estimated_minutes=int(item.get("estimated_minutes") or 40),
                ai_description=item.get("description"),
            )
            self.db.add(task)
            self.db.flush()
            created.append(task)
        self.db.commit()
        return created
