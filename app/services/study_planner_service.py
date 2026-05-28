from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models import StudyTask
from app.services.planner_engine import (
    confirm_reschedule_plan,
    preview_reschedule_missed_tasks,
    prioritize_tasks,
)


class StudyPlannerService:
    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id

    def prioritize(self, weekly_priority: str = "Equilíbrio") -> dict[str, Any]:
        tasks = (
            self.db.query(StudyTask)
            .filter(StudyTask.user_id == self.user_id)
            .filter(StudyTask.status.in_(["pending", "late", "rescheduled", "pendente", "atrasada", "reagendada"]))
            .all()
        )
        ordered = prioritize_tasks(tasks, weekly_priority)
        today = date.today()
        items = []
        for item in ordered[:20]:
            deadline = item.due_date or item.deadline
            items.append(
                {
                    "id": item.id,
                    "title": item.title,
                    "subject": item.subject or (item.subject_ref.name if item.subject_ref else None),
                    "priority": item.priority,
                    "status": item.status,
                    "estimated_minutes": item.estimated_minutes,
                    "deadline": deadline.isoformat() if deadline else None,
                    "is_overdue": bool(deadline and deadline < today and (item.status or "").lower() not in {"completed", "concluída"}),
                }
            )
        return {"tasks": items}

    def preview_reorganize_week(self) -> dict[str, Any]:
        return preview_reschedule_missed_tasks(self.user_id, "Recuperação", self.db)

    def apply_reorganize_week(self, preview: list[dict[str, Any]]) -> dict[str, Any]:
        return confirm_reschedule_plan(self.user_id, preview, self.db)
