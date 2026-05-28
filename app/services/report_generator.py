from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Essay, ExamResult, Flashcard, StudyTask
from app.services.ai_gateway import AIGateway
from app.services.performance_analyzer import detect_weak_subjects, recommend_next_focus
from app.services.planner_engine import detect_overload


def _get_db(db: Session | None) -> tuple[Session, bool]:
    if db:
        return db, False
    return SessionLocal(), True


def generate_weekly_report(user_id: int, db: Session | None = None) -> dict[str, object]:
    db, owns_session = _get_db(db)
    try:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        tasks = db.query(StudyTask).filter(StudyTask.user_id == user_id).all()
        completed = [task for task in tasks if task.status in {"completed", "concluída"}]
        delayed = [task for task in tasks if task.status in {"late", "atrasada"} or ((task.due_date or task.deadline) and (task.due_date or task.deadline) < today and task.status not in {"completed", "concluída"})]
        planned = sum(task.estimated_minutes or 0 for task in tasks if not (task.due_date or task.deadline) or (task.due_date or task.deadline) >= week_start)
        completed_minutes = sum(task.estimated_minutes or 0 for task in completed)
        subject_minutes: dict[str, int] = {}
        for task in completed:
            subject_minutes[task.subject or "geral"] = subject_minutes.get(task.subject or "geral", 0) + (task.estimated_minutes or 0)
        most_studied = max(subject_minutes.items(), key=lambda item: item[1])[0] if subject_minutes else "ainda sem registro"
        due_cards = db.query(Flashcard).filter(Flashcard.user_id == user_id).count()
        exams = db.query(ExamResult).filter(ExamResult.user_id == user_id).count()
        essays = db.query(Essay).filter(Essay.user_id == user_id).count()
        report = {
            "week_start": week_start.isoformat(),
            "completed_tasks": len(completed),
            "delayed_tasks": len(delayed),
            "planned_minutes": planned,
            "completed_minutes": completed_minutes,
            "most_studied_subject": most_studied,
            "weakest_subjects": detect_weak_subjects(user_id, db),
            "revision_total": due_cards,
            "exam_count": exams,
            "essay_count": essays,
            "overload": detect_overload(user_id, db),
            "recommended_focus": recommend_next_focus(user_id, db),
        }
        response = AIGateway(db, user_id).generate_text(
            "reports",
            "weekly_report",
            "Gere uma análise semanal curta do AprovaOS. Use apenas organização, carga realista, revisão ativa e próximos passos. Não prometa aprovação.",
            f"Relatório semanal estruturado: {report}",
            max_tokens=800,
        )
        report["ai_analysis"] = response.text if response.used_ai else response.friendly_message
        report["ai_configured"] = response.used_ai
        return report
    finally:
        if owns_session:
            db.close()
