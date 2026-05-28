from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RoutineBlock, StudyTask, Subject, SubjectFront, SubjectTopic, UserProfile
from app.routers.auth import app_context, get_current_user, login_redirect, require_api_user, templates
from app.schemas import (
    RoutineBlockCreate,
    RoutineBlockUpdate,
    RoutinePlannerConfirmRequest,
    RoutinePlannerRequest,
    RoutineProfileUpdate,
    TaskCreate,
    TaskUpdate,
)
from app.services.routine_planner_service import suggest_routine_blocks


router = APIRouter()


@router.get("/app/routine")
def routine_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    return templates.TemplateResponse(request, "routine.html", app_context(request, user, "routine", "Rotina"))


@router.get("/app/pending")
def pending_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    return templates.TemplateResponse(request, "pending.html", app_context(request, user, "pending", "Pendências"))


@router.get("/api/routine")
def list_routine(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    blocks = db.query(RoutineBlock).filter(RoutineBlock.user_id == current_user.id).order_by(RoutineBlock.weekday, RoutineBlock.start_time).all()
    return {"blocks": [_routine_dict(block) for block in blocks]}


@router.post("/api/routine")
def create_routine(payload: RoutineBlockCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    data = payload.model_dump()
    data["type"] = data["block_type"]
    data["day_of_week"] = data["weekday"]
    block = RoutineBlock(user_id=current_user.id, **data)
    db.add(block)
    db.commit()
    db.refresh(block)
    return {"message": "Bloco de rotina criado.", "block": _routine_dict(block)}


@router.put("/api/routine/blocks/{block_id}")
def update_routine(block_id: int, payload: RoutineBlockUpdate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    block = db.query(RoutineBlock).filter(RoutineBlock.id == block_id, RoutineBlock.user_id == current_user.id).first()
    if not block:
        raise HTTPException(status_code=404, detail="Bloco não encontrado.")
    for key, value in payload.model_dump().items():
        setattr(block, key, value)
    block.type = block.block_type
    block.day_of_week = block.weekday
    block.description = block.description or block.notes
    db.commit()
    return {"message": "Bloco atualizado.", "block": _routine_dict(block)}


@router.delete("/api/routine/blocks/{block_id}")
def delete_routine(block_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    block = db.query(RoutineBlock).filter(RoutineBlock.id == block_id, RoutineBlock.user_id == current_user.id).first()
    if not block:
        raise HTTPException(status_code=404, detail="Bloco não encontrado.")
    db.delete(block)
    db.commit()
    return {"message": "Bloco removido."}


@router.post("/api/routine/blocks/{block_id}/duplicate")
def duplicate_routine(block_id: int, payload: dict, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    block = db.query(RoutineBlock).filter(RoutineBlock.id == block_id, RoutineBlock.user_id == current_user.id).first()
    if not block:
        raise HTTPException(status_code=404, detail="Bloco não encontrado.")

    weekdays = payload.get("weekdays") if isinstance(payload, dict) else []
    if not isinstance(weekdays, list) or not weekdays:
        raise HTTPException(status_code=400, detail="Informe os dias da semana para duplicar.")

    created = 0
    for weekday in weekdays:
        try:
            weekday_int = int(weekday)
        except (TypeError, ValueError):
            continue
        if weekday_int < 0 or weekday_int > 6:
            continue
        new_block = RoutineBlock(
            user_id=current_user.id,
            title=block.title,
            block_type=block.block_type,
            type=block.type or block.block_type,
            weekday=weekday_int,
            day_of_week=weekday_int,
            start_time=block.start_time,
            end_time=block.end_time,
            recurrence=block.recurrence,
            notes=block.notes,
            description=block.description,
        )
        db.add(new_block)
        created += 1
    db.commit()
    return {"message": f"{created} blocos duplicados.", "created": created}


@router.get("/api/routine/profile")
def get_routine_profile(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    profile = _get_or_create_profile(current_user.id, db)
    return {"profile": _profile_dict(profile)}


@router.put("/api/routine/profile")
def update_routine_profile(payload: RoutineProfileUpdate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    profile = _get_or_create_profile(current_user.id, db)
    for key, value in payload.model_dump().items():
        if value is not None:
            setattr(profile, key, value)

    if payload.vestibulares_alvo is not None:
        profile.target_exams = payload.vestibulares_alvo
    if payload.serie is not None:
        profile.school_year = payload.serie
    if payload.principais_dificuldades is not None:
        profile.main_difficulty = payload.principais_dificuldades
    if payload.rotina_resumo is not None:
        profile.study_profile_summary = payload.rotina_resumo

    db.add(profile)
    db.commit()
    db.refresh(profile)
    return {"message": "Perfil de rotina atualizado.", "profile": _profile_dict(profile)}


@router.post("/api/routine/planner/preview")
def routine_planner_preview(payload: RoutinePlannerRequest, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    suggestions = suggest_routine_blocks(payload.message)
    if not suggestions:
        return {"message": "Não consegui montar sugestão com essa frase. Tente informar dias e duração.", "suggestions": []}
    return {"message": "Sugestão pronta. Revise antes de salvar.", "suggestions": suggestions}


@router.post("/api/routine/planner/confirm")
def routine_planner_confirm(payload: RoutinePlannerConfirmRequest, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    created = 0
    for item in payload.suggestions:
        try:
            validated = RoutineBlockCreate(**item)
        except Exception:
            continue
        data = validated.model_dump()
        data["type"] = data["block_type"]
        data["day_of_week"] = data["weekday"]
        block = RoutineBlock(user_id=current_user.id, **data)
        db.add(block)
        created += 1
    db.commit()
    return {"message": f"{created} blocos adicionados pela sugestão.", "created": created}


@router.get("/api/tasks")
def list_tasks(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    tasks = db.query(StudyTask).filter(StudyTask.user_id == current_user.id).order_by(StudyTask.deadline.asc().nulls_last(), StudyTask.created_at.desc()).all()
    return {"tasks": [_task_dict(task) for task in tasks], "summary": _task_summary(tasks)}


@router.get("/api/pending-tasks")
def list_pending_tasks(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    return list_tasks(current_user, db)


@router.post("/api/tasks")
def create_task(payload: TaskCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    data = payload.model_dump()
    _attach_subject_data(data, current_user.id, db)
    task = StudyTask(user_id=current_user.id, **data)
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"message": "Pendência criada.", "task": _task_dict(task)}


@router.post("/api/pending-tasks")
def create_pending_task(payload: TaskCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    return create_task(payload, current_user, db)


@router.put("/api/tasks/{task_id}")
def update_task(task_id: int, payload: TaskUpdate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    task = db.query(StudyTask).filter(StudyTask.id == task_id, StudyTask.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")

    updates = payload.model_dump()
    _attach_subject_data(updates, current_user.id, db)
    for key, value in updates.items():
        setattr(task, key, value)

    if task.due_date and not task.deadline:
        task.deadline = task.due_date
    if task.deadline and not task.due_date:
        task.due_date = task.deadline
    if task.source and not task.source_type:
        task.source_type = task.source
    if task.source_type and not task.source:
        task.source = task.source_type
    if task.origin is None:
        task.origin = task.source or task.source_type

    if task.status in {"completed", "concluída"}:
        task.completed_at = task.completed_at or datetime.now()

    db.commit()
    return {"message": "Pendência atualizada.", "task": _task_dict(task)}


@router.put("/api/pending-tasks/{task_id}")
def update_pending_task(task_id: int, payload: TaskUpdate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    return update_task(task_id, payload, current_user, db)


@router.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    task = db.query(StudyTask).filter(StudyTask.id == task_id, StudyTask.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")
    task.status = "completed"
    task.completed_at = datetime.now()
    db.commit()
    return {"message": "Pendência concluída.", "task": _task_dict(task)}


@router.post("/api/tasks/{task_id}/miss")
def miss_task(task_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    task = db.query(StudyTask).filter(StudyTask.id == task_id, StudyTask.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")
    task.status = "late"
    db.commit()
    return {"message": "Sem culpa. A pendência foi marcada para reorganização.", "task": _task_dict(task)}


@router.post("/api/tasks/{task_id}/status")
def update_task_status(task_id: int, payload: dict, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    task = db.query(StudyTask).filter(StudyTask.id == task_id, StudyTask.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")

    status = str(payload.get("status") or "").strip().lower()
    valid = {"pending", "completed", "late", "rescheduled", "pendente", "concluída", "atrasada", "reagendada"}
    if status not in valid:
        raise HTTPException(status_code=400, detail="Status inválido.")

    task.status = status
    if status in {"completed", "concluída"}:
        task.completed_at = datetime.now()
    db.commit()
    return {"message": "Status atualizado.", "task": _task_dict(task)}


@router.post("/api/tasks/{task_id}/reschedule")
def reschedule_task(task_id: int, payload: dict, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    task = db.query(StudyTask).filter(StudyTask.id == task_id, StudyTask.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")

    deadline_raw = str(payload.get("deadline") or "").strip()
    if not deadline_raw:
        raise HTTPException(status_code=400, detail="Informe a nova data para reagendar.")
    try:
        new_deadline = date.fromisoformat(deadline_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Data de reagendamento inválida.") from exc

    task.deadline = new_deadline
    task.due_date = new_deadline
    task.status = "rescheduled"
    db.commit()
    return {"message": "Pendência reagendada.", "task": _task_dict(task)}


@router.delete("/api/tasks/{task_id}")
def delete_task(task_id: int, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    task = db.query(StudyTask).filter(StudyTask.id == task_id, StudyTask.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Pendência não encontrada.")
    db.delete(task)
    db.commit()
    return {"message": "Pendência removida."}


def _routine_dict(block: RoutineBlock) -> dict[str, object]:
    return {
        "id": block.id,
        "title": block.title,
        "block_type": block.block_type,
        "type": block.type or block.block_type,
        "weekday": block.weekday,
        "day_of_week": block.day_of_week if block.day_of_week is not None else block.weekday,
        "start_time": block.start_time.isoformat(timespec="minutes"),
        "end_time": block.end_time.isoformat(timespec="minutes"),
        "recurrence": block.recurrence,
        "notes": block.notes,
        "description": block.description or block.notes,
    }


def _profile_dict(profile: UserProfile) -> dict[str, object]:
    return {
        "vestibulares_alvo": profile.vestibulares_alvo or profile.target_exams,
        "serie": profile.serie or profile.school_year,
        "rotina_resumo": profile.rotina_resumo or profile.study_profile_summary,
        "carga_horaria_disponivel": profile.carga_horaria_disponivel,
        "principais_dificuldades": profile.principais_dificuldades or profile.main_difficulty,
        "metas": profile.metas,
        "observacoes": profile.observacoes,
        "weekly_priority": profile.weekly_priority,
        "overload_risk": profile.overload_risk,
    }


def _task_dict(task: StudyTask) -> dict[str, object]:
    return {
        "id": task.id,
        "material_id": task.material_id,
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
        "subtopic": task.subtopic,
        "source_type": task.source_type,
        "priority": task.priority,
        "status": task.status,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "due_date": (task.due_date or task.deadline).isoformat() if (task.due_date or task.deadline) else None,
        "estimated_minutes": task.estimated_minutes,
        "ai_description": task.ai_description,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


def _attach_subject_data(data: dict[str, object], user_id: int, db: Session) -> None:
    subject_id = data.get("subject_id")
    if subject_id:
        subject = db.query(Subject).filter(Subject.id == int(subject_id), Subject.user_id == user_id).first()
        if subject:
            data["subject"] = subject.name

    front_id = data.get("front_id")
    if front_id:
        front = (
            db.query(SubjectFront)
            .join(Subject, Subject.id == SubjectFront.subject_id)
            .filter(SubjectFront.id == int(front_id), Subject.user_id == user_id)
            .first()
        )
        if front and not data.get("subject_id"):
            data["subject_id"] = front.subject_id

    topic_id = data.get("topic_id")
    if topic_id:
        topic = (
            db.query(SubjectTopic)
            .join(Subject, Subject.id == SubjectTopic.subject_id)
            .filter(SubjectTopic.id == int(topic_id), Subject.user_id == user_id)
            .first()
        )
        if topic:
            if not data.get("front_id") and topic.front_id:
                data["front_id"] = topic.front_id
            if not data.get("subject_id"):
                data["subject_id"] = topic.subject_id
            if not data.get("subtopic"):
                data["subtopic"] = topic.name

    data["origin"] = data.get("origin") or data.get("source") or data.get("source_type")


def _get_or_create_profile(user_id: int, db: Session) -> UserProfile:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile:
        return profile
    profile = UserProfile(user_id=user_id)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _task_summary(tasks: list[StudyTask]) -> dict[str, int]:
    today = date.today()
    overdue = 0
    today_count = 0
    next_7_days = 0
    high_priority = 0
    for task in tasks:
        due = task.due_date or task.deadline
        status = (task.status or "").lower()
        if task.priority in {"alta", "urgente"}:
            high_priority += 1
        if due:
            if due < today and status not in {"completed", "concluída"}:
                overdue += 1
            if due == today and status not in {"completed", "concluída"}:
                today_count += 1
            if today <= due <= (today + timedelta(days=7)) and status not in {"completed", "concluída"}:
                next_7_days += 1
    return {
        "overdue": overdue,
        "today": today_count,
        "next_7_days": next_7_days,
        "high_priority": high_priority,
    }


