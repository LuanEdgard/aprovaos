from sqlalchemy.orm import Session

from app.models import CalendarEvent, Essay, ExamResult, Flashcard, Material, RoutineBlock, StudyTask, Subject, User
from app.services.ai_utils import truncate_text


def build_student_context(user: User, db: Session) -> dict[str, object]:
    user_id = user.id
    profile = user.profile
    return {
        "perfil": {
            "nome": user.name,
            "idade": user.age,
            "serie_ou_situacao": profile.school_year if profile else None,
            "prioridade_semana": profile.weekly_priority if profile else None,
            "dificuldade_principal": profile.main_difficulty if profile else None,
            "resumo": profile.study_profile_summary if profile else None,
        },
        "rotina": [_routine(block) for block in db.query(RoutineBlock).filter(RoutineBlock.user_id == user_id).order_by(RoutineBlock.weekday, RoutineBlock.start_time).limit(30)],
        "materias": [_subject(subject) for subject in db.query(Subject).filter(Subject.user_id == user_id, Subject.is_active == True).limit(30)],  # noqa: E712
        "pendencias": [_task(task) for task in db.query(StudyTask).filter(StudyTask.user_id == user_id).order_by(StudyTask.deadline.asc().nulls_last()).limit(30)],
        "materiais": [_material(material) for material in db.query(Material).filter(Material.user_id == user_id).order_by(Material.created_at.desc()).limit(12)],
        "flashcards": _flashcard_stats(user_id, db),
        "simulados": [_exam(exam) for exam in db.query(ExamResult).filter(ExamResult.user_id == user_id).order_by(ExamResult.date.desc()).limit(8)],
        "redacoes": [_essay(essay) for essay in db.query(Essay).filter(Essay.user_id == user_id).order_by(Essay.date.desc()).limit(8)],
        "calendario": [_event(event) for event in db.query(CalendarEvent).filter(CalendarEvent.user_id == user_id).order_by(CalendarEvent.start_datetime.asc()).limit(20)],
    }


def _routine(block: RoutineBlock) -> dict[str, object]:
    return {
        "titulo": block.title,
        "tipo": block.type or block.block_type,
        "dia": block.day_of_week if block.day_of_week is not None else block.weekday,
        "inicio": block.start_time.isoformat(timespec="minutes"),
        "fim": block.end_time.isoformat(timespec="minutes"),
        "descricao": block.description or block.notes,
    }


def _subject(subject: Subject) -> dict[str, object]:
    return {"id": subject.id, "nome": subject.name, "area": subject.area, "origem": subject.source_type, "descricao": subject.description}


def _task(task: StudyTask) -> dict[str, object]:
    return {
        "id": task.id,
        "titulo": task.title,
        "descricao": truncate_text(task.description or task.ai_description, 300),
        "categoria": task.task_category,
        "fonte": task.source or task.source_type,
        "materia": task.subject_ref.name if task.subject_ref else task.subject,
        "subtopico": task.subtopic,
        "status": task.status,
        "prazo": (task.due_date or task.deadline).isoformat() if (task.due_date or task.deadline) else None,
        "minutos": task.estimated_minutes,
    }


def _material(material: Material) -> dict[str, object]:
    return {
        "id": material.id,
        "titulo": material.title,
        "tipo": material.type or material.material_type,
        "fonte": material.source or material.source_type,
        "materia": material.subject_ref.name if material.subject_ref else material.subject,
        "topico": material.topic,
        "subtopico": material.subtopic,
        "tags": material.tags,
        "resumo": truncate_text(material.ai_summary or material.summary, 500),
    }


def _flashcard_stats(user_id: int, db: Session) -> dict[str, object]:
    cards = db.query(Flashcard).filter(Flashcard.user_id == user_id).all()
    due = [card for card in cards if not card.next_review_at]
    return {"total": len(cards), "sem_data_de_revisao": len(due)}


def _exam(exam: ExamResult) -> dict[str, object]:
    return {"tipo": exam.exam_type, "data": exam.date.isoformat(), "nota": exam.total_score, "motivo_erro": exam.error_reason, "erros": truncate_text(exam.main_mistakes, 220)}


def _essay(essay: Essay) -> dict[str, object]:
    return {"tema": essay.theme, "data": essay.date.isoformat(), "nota_estimada": essay.total_score, "erros": truncate_text(essay.recurring_errors, 220), "observacao": "registro de evolução, não correção oficial"}


def _event(event: CalendarEvent) -> dict[str, object]:
    return {"titulo": event.title, "tipo": event.event_type, "inicio": event.start_datetime.isoformat(), "fim": event.end_datetime.isoformat() if event.end_datetime else None, "descricao": event.description or event.notes}
