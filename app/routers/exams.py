from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ExamResult
from app.routers.auth import app_context, get_current_user, login_redirect, require_api_user, templates
from app.schemas import ExamCreate
from app.services.performance_analyzer import analyze_exam_results


router = APIRouter()


@router.get("/app/exams")
def exams_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    return templates.TemplateResponse(request, "exams.html", app_context(request, user, "exams", "Simulados"))


@router.get("/api/exams")
def list_exams(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    exams = db.query(ExamResult).filter(ExamResult.user_id == current_user.id).order_by(ExamResult.date.asc()).all()
    return {"exams": [_exam_dict(exam) for exam in exams], "analysis": analyze_exam_results(current_user.id, db)}


@router.get("/api/simulations")
def list_simulations(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    return list_exams(current_user, db)


@router.post("/api/exams")
def create_exam(payload: ExamCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    exam = ExamResult(user_id=current_user.id, **payload.model_dump())
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return {"message": "Simulado registrado.", "exam": _exam_dict(exam)}


@router.post("/api/simulations")
def create_simulation(payload: ExamCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    return create_exam(payload, current_user, db)


def _exam_dict(exam: ExamResult) -> dict[str, object]:
    return {
        "id": exam.id,
        "exam_type": exam.exam_type,
        "date": exam.date.isoformat(),
        "total_score": exam.total_score,
        "score_languages": exam.score_languages,
        "score_human_sciences": exam.score_human_sciences,
        "score_natural_sciences": exam.score_natural_sciences,
        "score_math": exam.score_math,
        "essay_score": exam.essay_score,
        "score_by_area": exam.score_by_area,
        "correct_by_subject": exam.correct_by_subject,
        "duration_minutes": exam.duration_minutes,
        "notes": exam.notes,
        "main_mistakes": exam.main_mistakes,
        "error_reason": exam.error_reason,
    }
