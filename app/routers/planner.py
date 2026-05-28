from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CalendarEvent
from app.routers.auth import app_context, get_current_user, login_redirect, require_api_user, templates
from app.schemas import CalendarEventCreate, RescheduleRequest, WeeklyPriorityRequest
from app.services.calendar_service import google_export_status, internal_calendar_items
from app.services.planner_engine import confirm_reschedule_plan, preview_reschedule_missed_tasks, reschedule_missed_tasks


router = APIRouter()


@router.get("/app/calendar")
def calendar_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    return templates.TemplateResponse(request, "calendar.html", app_context(request, user, "calendar", "Calendário"))


@router.get("/api/calendar")
def list_calendar(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    events = db.query(CalendarEvent).filter(CalendarEvent.user_id == current_user.id).order_by(CalendarEvent.start_datetime.asc()).all()
    return {"events": [_event_dict(event) for event in events], "items": internal_calendar_items(current_user.id, db), "google": google_export_status()}


@router.post("/api/calendar")
def create_calendar_event(payload: CalendarEventCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    event = CalendarEvent(user_id=current_user.id, source_type="manual", source_id=None, external_id=None, **payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"message": "Evento criado.", "event": _event_dict(event)}


@router.post("/api/calendar/export/google")
def export_google_calendar(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    return google_export_status()


@router.put("/api/calendar/{event_id}")
def update_calendar_event(event_id: int, payload: CalendarEventCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    event = db.query(CalendarEvent).filter(CalendarEvent.id == event_id, CalendarEvent.user_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Evento não encontrado.")
    for key, value in payload.model_dump().items():
        setattr(event, key, value)
    event.source_type = event.source_type or "manual"
    db.commit()
    return {"message": "Evento atualizado.", "event": _event_dict(event)}


@router.delete("/api/calendar/{event_id}")
def delete_calendar_event(event_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    event = db.query(CalendarEvent).filter(CalendarEvent.id == event_id, CalendarEvent.user_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Evento não encontrado.")
    db.delete(event)
    db.commit()
    return {"message": "Evento removido."}


@router.post("/api/tasks/reschedule")
def reschedule_tasks(payload: RescheduleRequest, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    return reschedule_missed_tasks(current_user.id, payload.mode, db)


@router.post("/api/tasks/reschedule/preview")
def reschedule_tasks_preview(payload: RescheduleRequest, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    return preview_reschedule_missed_tasks(current_user.id, payload.mode, db)


@router.post("/api/tasks/reschedule/confirm")
def reschedule_tasks_confirm(payload: dict, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    preview = payload.get("preview") if isinstance(payload, dict) else []
    if not isinstance(preview, list):
        raise HTTPException(status_code=400, detail="Preview inválido.")
    return confirm_reschedule_plan(current_user.id, preview, db)


@router.post("/api/planner/priority")
def update_weekly_priority(payload: WeeklyPriorityRequest, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    if current_user.profile:
        current_user.profile.weekly_priority = payload.weekly_priority
        db.commit()
    return {"message": f"Prioridade da semana ajustada para {payload.weekly_priority}."}


def _event_dict(event: CalendarEvent) -> dict[str, object]:
    return {
        "id": event.id,
        "title": event.title,
        "event_type": event.event_type,
        "start_datetime": event.start_datetime.isoformat(),
        "end_datetime": event.end_datetime.isoformat() if event.end_datetime else None,
        "related_task_id": event.related_task_id,
        "notes": event.notes,
        "description": event.description or event.notes,
        "status": event.status,
        "source_type": event.source_type,
        "source_id": event.source_id,
        "external_id": event.external_id,
    }
