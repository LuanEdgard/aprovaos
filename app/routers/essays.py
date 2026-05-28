from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Essay
from app.routers.auth import app_context, get_current_user, login_redirect, require_api_user, templates
from app.schemas import EssayCreate
from app.services.performance_analyzer import analyze_essay_progress


router = APIRouter()


@router.get("/app/essays")
def essays_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    return templates.TemplateResponse(request, "essays.html", app_context(request, user, "essays", "Redação"))


@router.get("/api/essays")
def list_essays(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    essays = db.query(Essay).filter(Essay.user_id == current_user.id).order_by(Essay.date.asc()).all()
    return {"essays": [_essay_dict(essay) for essay in essays], "analysis": analyze_essay_progress(current_user.id, db)}


@router.post("/api/essays")
def create_essay(payload: EssayCreate, current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    essay = Essay(user_id=current_user.id, **payload.model_dump())
    db.add(essay)
    db.commit()
    db.refresh(essay)
    return {"message": "Redação registrada como estimativa e histórico de evolução.", "essay": _essay_dict(essay)}


def _essay_dict(essay: Essay) -> dict[str, object]:
    return {
        "id": essay.id,
        "theme": essay.theme,
        "date": essay.date.isoformat(),
        "total_score": essay.total_score,
        "c1": essay.c1,
        "c2": essay.c2,
        "c3": essay.c3,
        "c4": essay.c4,
        "c5": essay.c5,
        "corrector_feedback": essay.corrector_feedback,
        "teacher_comments": essay.teacher_comments or essay.corrector_feedback,
        "recurring_errors": essay.recurring_errors,
        "repertoires_used": essay.repertoires_used,
        "repertoire_used": essay.repertoire_used or essay.repertoires_used,
        "intervention_notes": essay.intervention_notes,
        "improvement_points": essay.improvement_points or essay.intervention_notes,
    }
