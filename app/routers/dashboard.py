from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CalendarEvent, Essay, Flashcard, RoutineBlock, StudyTask, UserSettings
from app.routers.auth import app_context, get_current_user, login_redirect, require_api_user, templates
from app.schemas import SettingsUpdate
from app.services.performance_analyzer import detect_weak_subjects, recommend_next_focus
from app.services.planner_engine import detect_overload, prioritize_tasks


router = APIRouter()


@router.get("/")
def landing_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return templates.TemplateResponse(request, "landing.html", app_context(request, user, "landing", "AprovaOS"))


@router.get("/app/dashboard")
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    return templates.TemplateResponse(request, "dashboard.html", app_context(request, user, "dashboard", "Hoje"))


@router.get("/app/settings")
def settings_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    return templates.TemplateResponse(request, "settings.html", app_context(request, user, "settings", "Configurações"))


@router.get("/api/dashboard/summary")
def dashboard_summary(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    today = date.today()
    today_start = datetime.combine(today, time.min)
    next_week = today + timedelta(days=7)
    tasks = db.query(StudyTask).filter(StudyTask.user_id == current_user.id).all()
    active_tasks = [task for task in tasks if task.status not in {"completed", "concluída"}]
    ordered = prioritize_tasks(active_tasks, current_user.profile.weekly_priority if current_user.profile else "Equilíbrio")
    overdue = [task for task in active_tasks if (task.due_date or task.deadline) and (task.due_date or task.deadline) < today]
    today_tasks = [task for task in ordered if not (task.due_date or task.deadline) or (task.due_date or task.deadline) <= today][:10]
    upcoming_tasks = [task for task in ordered if (task.due_date or task.deadline) and today < (task.due_date or task.deadline) <= next_week][:8]
    next_exam_event = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.user_id == current_user.id, CalendarEvent.event_type.in_(["simulado", "prova"]), CalendarEvent.start_datetime >= today_start)
        .order_by(CalendarEvent.start_datetime.asc())
        .first()
    )
    next_essay = db.query(Essay).filter(Essay.user_id == current_user.id).order_by(Essay.date.desc()).first()
    due_cards_query = db.query(Flashcard).filter(Flashcard.user_id == current_user.id).filter((Flashcard.next_review_at == None) | (Flashcard.next_review_at <= datetime.now()))  # noqa: E711
    due_cards = due_cards_query.count()
    due_cards_items = due_cards_query.limit(10).all()
    completed_week = [task for task in tasks if task.status in {"completed", "concluída"} and task.created_at.date() >= today - timedelta(days=today.weekday())]
    planned_minutes = sum(task.estimated_minutes or 0 for task in active_tasks if not (task.due_date or task.deadline) or (task.due_date or task.deadline) <= next_week)
    completed_minutes = sum(task.estimated_minutes or 0 for task in completed_week)
    weekly_priority = current_user.profile.weekly_priority if current_user.profile else "Equilíbrio"
    timeline = _build_today_timeline(current_user.id, today, today_tasks, db)

    kanban = {
        "today": [_task_dict(task) for task in today_tasks if task.status not in {"completed", "concluída"}],
        "in_progress": [_task_dict(task) for task in active_tasks if task.status in {"rescheduled", "reagendada"}][:10],
        "overdue": [_task_dict(task) for task in overdue[:10]],
        "completed": [_task_dict(task) for task in tasks if task.status in {"completed", "concluída"}][:10],
    }
    return {
        "student_name": current_user.name,
        "today_date": today.isoformat(),
        "weekly_priority": weekly_priority,
        "today_plan": [_task_dict(task) for task in today_tasks],
        "kanban": kanban,
        "timeline": timeline,
        "pending_count": len(active_tasks),
        "overdue_count": len(overdue),
        "overdue_tasks": [_task_dict(task) for task in overdue[:5]],
        "revision_count": due_cards,
        "due_flashcards": [_flashcard_dict(card) for card in due_cards_items],
        "upcoming_tasks": [_task_dict(task) for task in upcoming_tasks],
        "next_exam": _event_dict(next_exam_event),
        "next_simulation": _event_dict(next_exam_event),
        "next_essay": _essay_dict(next_essay),
        "week_progress": {"completed": len(completed_week), "total": max(len(active_tasks) + len(completed_week), 1)},
        "study_load": {"planned_minutes": planned_minutes, "completed_minutes": completed_minutes},
        "risk_subjects": detect_weak_subjects(current_user.id, db),
        "overload": detect_overload(current_user.id, db),
        "next_focus": recommend_next_focus(current_user.id, db),
    }


@router.get("/api/settings")
def get_settings(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    settings = _get_or_create_settings(current_user.id, db)
    return {"settings": _settings_dict(settings)}


@router.post("/api/settings")
def update_settings(payload: SettingsUpdate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    settings = _get_or_create_settings(current_user.id, db)
    settings.theme = payload.theme
    settings.notify_reviews = "sim" if payload.notify_reviews else "não"
    settings.notify_weekly_summary = "sim" if payload.notify_weekly_summary else "não"
    db.commit()
    db.refresh(settings)
    return {"message": "Preferências salvas.", "settings": _settings_dict(settings)}


def _task_dict(task: StudyTask) -> dict[str, object]:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "task_category": task.task_category,
        "source": task.source or task.source_type,
        "origin": task.origin or task.source or task.source_type,
        "subject_id": task.subject_id,
        "front_id": task.front_id,
        "topic_id": task.topic_id,
        "subject": task.subject,
        "front": task.front_ref.name if task.front_ref else None,
        "topic": task.topic_ref.name if task.topic_ref else None,
        "source_type": task.source_type,
        "priority": task.priority,
        "status": task.status,
        "deadline": (task.due_date or task.deadline).isoformat() if (task.due_date or task.deadline) else None,
        "due_date": (task.due_date or task.deadline).isoformat() if (task.due_date or task.deadline) else None,
        "estimated_minutes": task.estimated_minutes,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


def _event_dict(event: CalendarEvent | None) -> dict[str, object] | None:
    if not event:
        return None
    return {
        "id": event.id,
        "title": event.title,
        "event_type": event.event_type,
        "start_datetime": event.start_datetime.isoformat(),
        "status": event.status,
    }


def _essay_dict(essay: Essay | None) -> dict[str, object] | None:
    if not essay:
        return None
    return {"id": essay.id, "theme": essay.theme, "date": essay.date.isoformat(), "total_score": essay.total_score}


def _flashcard_dict(card: Flashcard) -> dict[str, object]:
    return {
        "id": card.id,
        "front": card.front,
        "subject": card.subject,
        "topic": card.topic,
        "next_review_at": card.next_review_at.isoformat() if card.next_review_at else None,
    }


def _build_today_timeline(user_id: int, today: date, today_tasks: list[StudyTask], db: Session) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    routine_blocks = (
        db.query(RoutineBlock)
        .filter(RoutineBlock.user_id == user_id, RoutineBlock.weekday == today.weekday())
        .order_by(RoutineBlock.start_time.asc())
        .all()
    )
    for block in routine_blocks:
        items.append(
            {
                "kind": "fixed",
                "title": block.title,
                "start_time": block.start_time.strftime("%H:%M"),
                "end_time": block.end_time.strftime("%H:%M"),
                "type": block.type or block.block_type,
            }
        )

    routine = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.user_id == user_id)
        .filter(CalendarEvent.start_datetime >= datetime.combine(today, time.min))
        .filter(CalendarEvent.start_datetime <= datetime.combine(today, time.max))
        .order_by(CalendarEvent.start_datetime.asc())
        .all()
    )
    for event in routine:
        items.append(
            {
                "kind": "fixed",
                "title": event.title,
                "start_time": event.start_datetime.strftime("%H:%M"),
                "end_time": event.end_datetime.strftime("%H:%M") if event.end_datetime else None,
                "type": event.event_type,
            }
        )

    cursor = datetime.combine(today, time(18, 0))
    for task in today_tasks[:8]:
        start = cursor
        end = start + timedelta(minutes=max(20, min(task.estimated_minutes or 50, 120)))
        items.append(
            {
                "kind": "task",
                "title": task.title,
                "start_time": start.strftime("%H:%M"),
                "end_time": end.strftime("%H:%M"),
                "type": "estudo",
                "task_id": task.id,
            }
        )
        cursor = end + timedelta(minutes=10)

    if len(items) < 2:
        items.append({"kind": "free", "title": "Janela livre", "start_time": "19:00", "end_time": "21:00", "type": "livre"})
    return sorted(items, key=lambda item: item.get("start_time") or "")


def _get_or_create_settings(user_id: int, db: Session) -> UserSettings:
    settings = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
    if settings:
        return settings
    settings = UserSettings(user_id=user_id)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def _settings_dict(settings: UserSettings) -> dict[str, object]:
    return {
        "theme": settings.theme,
        "notify_reviews": settings.notify_reviews == "sim",
        "notify_weekly_summary": settings.notify_weekly_summary == "sim",
    }
