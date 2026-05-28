from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AIPlan
from app.routers.auth import app_context, get_current_user, login_redirect, require_api_user, templates
from app.services.report_generator import generate_weekly_report


router = APIRouter()


@router.get("/app/reports")
def reports_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    return templates.TemplateResponse(request, "reports.html", app_context(request, user, "reports", "Relatórios"))


@router.get("/api/reports/weekly")
def weekly_report(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    return generate_weekly_report(current_user.id, db)


@router.post("/api/reports/generate")
def generate_report(current_user=Depends(require_api_user), db: Session = Depends(get_db)):
    report = generate_weekly_report(current_user.id, db)
    plan = AIPlan(
        user_id=current_user.id,
        week_start=date.fromisoformat(report["week_start"]),
        weekly_priority=current_user.profile.weekly_priority if current_user.profile else "Equilíbrio",
        plan_text=f"Foco recomendado: {report['recommended_focus']}",
        rationale="Relatório semanal gerado a partir de tarefas, revisões, simulados e redações cadastrados.",
    )
    db.add(plan)
    db.commit()
    return {"message": "Relatório semanal gerado.", "report": report}
