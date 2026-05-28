from datetime import datetime, time, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models import CalendarEvent, Essay, ExamResult, Flashcard, RoutineBlock, StudyTask


def google_calendar_configured() -> bool:
    return bool(getattr(settings, "google_client_id", "") and getattr(settings, "google_client_secret", ""))


def internal_calendar_items(user_id: int, db: Session) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())

    for block in db.query(RoutineBlock).filter(RoutineBlock.user_id == user_id).all():
        weekday = block.day_of_week if block.day_of_week is not None else block.weekday
        day = week_start + timedelta(days=weekday)
        items.append(
            {
                "id": f"routine-{block.id}",
                "title": block.title,
                "event_type": block.type or block.block_type,
                "source": "routine",
                "source_type": "routine",
                "source_id": str(block.id),
                "start_datetime": datetime.combine(day, block.start_time).isoformat(),
                "end_datetime": datetime.combine(day, block.end_time).isoformat(),
                "status": "scheduled",
                "description": block.description or block.notes,
            }
        )

    for task in db.query(StudyTask).filter(StudyTask.user_id == user_id).all():
        due = task.due_date or task.deadline
        if due:
            items.append(
                {
                    "id": f"task-{task.id}",
                    "title": task.title,
                    "event_type": "pending_task",
                    "source": "task",
                    "source_type": "task",
                    "source_id": str(task.id),
                    "start_datetime": datetime.combine(due, time(18, 0)).isoformat(),
                    "end_datetime": datetime.combine(due, time(19, 0)).isoformat(),
                    "status": task.status,
                    "description": task.description,
                }
            )

    for exam in db.query(ExamResult).filter(ExamResult.user_id == user_id).all():
        items.append(_dated_item(f"simulation-{exam.id}", exam.exam_type, "simulation", exam.date.isoformat(), exam.notes))

    for essay in db.query(Essay).filter(Essay.user_id == user_id).all():
        items.append(_dated_item(f"essay-{essay.id}", essay.theme, "essay", essay.date.isoformat(), essay.recurring_errors))

    for card in db.query(Flashcard).filter(Flashcard.user_id == user_id, Flashcard.next_review_at.isnot(None)).limit(100):
        items.append(
            {
                "id": f"flashcard-{card.id}",
                "title": card.front[:80],
                "event_type": "flashcard_review",
                "source": "flashcard",
                "source_type": "flashcard",
                "source_id": str(card.id),
                "start_datetime": card.next_review_at.isoformat(),
                "end_datetime": None,
                "status": "pending",
                "description": card.topic,
            }
        )

    for event in db.query(CalendarEvent).filter(CalendarEvent.user_id == user_id).all():
        items.append(
            {
                "id": event.id,
                "title": event.title,
                "event_type": event.event_type,
                "source": "calendar",
                "source_type": event.source_type or "calendar",
                "source_id": event.source_id or str(event.id),
                "start_datetime": event.start_datetime.isoformat(),
                "end_datetime": event.end_datetime.isoformat() if event.end_datetime else None,
                "status": event.status,
                "description": event.description or event.notes,
            }
        )
    return sorted(items, key=lambda item: str(item["start_datetime"]))


def google_export_status() -> dict[str, object]:
    if not google_calendar_configured():
        return {
            "configured": False,
            "message": "Google Calendar não configurado. Use o calendário interno do AprovaOS ou configure as credenciais no .env.",
        }
    return {"configured": True, "message": "Credenciais encontradas. O fluxo OAuth ainda precisa ser conectado para exportar eventos com segurança."}


def _dated_item(item_id: str, title: str, event_type: str, iso_date: str, description: str | None) -> dict[str, object]:
    start = datetime.fromisoformat(iso_date)
    return {
        "id": item_id,
        "title": title,
        "event_type": event_type,
        "source": event_type,
        "source_type": event_type,
        "source_id": item_id,
        "start_datetime": datetime.combine(start.date(), time(9, 0)).isoformat(),
        "end_datetime": datetime.combine(start.date(), time(11, 0)).isoformat(),
        "status": "scheduled",
        "description": description,
    }
