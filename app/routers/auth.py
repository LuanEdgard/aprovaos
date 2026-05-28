from datetime import date, timedelta

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User, UserProfile
from app.schemas import LoginRequest, OnboardingRequest, SignupRequest
from app.services.routine_service import persist_onboarding_routine
from app.services.subject_service import ensure_default_subjects


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


NAV_ITEMS = [
    ("Hoje", "/app/dashboard", "layout-dashboard"),
    ("Rotina", "/app/routine", "calendar-clock"),
    ("Pendências", "/app/pending", "list-checks"),
    ("Matérias", "/app/subjects", "book-open"),
    ("Materiais", "/app/materials", "files"),
    ("Flashcards", "/app/flashcards", "copy-check"),
    ("Simulados", "/app/exams", "bar-chart-3"),
    ("Redação", "/app/essays", "pen-line"),
    ("Calendário", "/app/calendar", "calendar-days"),
    ("Tutor IA", "/app/tutor", "sparkles"),
    ("Relatórios", "/app/reports", "line-chart"),
    ("Configurações", "/app/settings", "settings"),
]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8")[:72], hashed_password.encode("utf-8"))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def require_api_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Sessão expirada. Entre novamente.")
    return user


def is_admin_user(user: User | None, db: Session | None = None) -> bool:
    if not user:
        return False
    if bool(getattr(user, "is_admin", False)):
        return True
    if user.email.lower() in settings.admin_emails:
        return True
    if db:
        first_user_id = db.query(User.id).order_by(User.id.asc()).limit(1).scalar()
        return first_user_id == user.id
    return False


def require_admin_user(current_user: User = Depends(require_api_user), db: Session = Depends(get_db)) -> User:
    if not is_admin_user(current_user, db):
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores do AprovaOS.")
    return current_user


def app_context(request: Request, user: User | None, page_id: str, title: str, **extra: object) -> dict[str, object]:
    context = {
        "request": request,
        "user": user,
        "page_id": page_id,
        "title": title,
        "app_page": bool(user and page_id not in {"landing", "login", "signup", "onboarding"}),
        "nav_items": NAV_ITEMS,
        "is_admin": is_admin_user(user, None),
        "ai_settings_ui_enabled": settings.ai_settings_ui_enabled,
    }
    context.update(extra)
    return context


def login_redirect() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse("/app/dashboard", status_code=303)
    return templates.TemplateResponse(request, "login.html", app_context(request, None, "login", "Entrar"))


@router.get("/signup")
def signup_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse("/onboarding", status_code=303)
    return templates.TemplateResponse(request, "signup.html", app_context(request, None, "signup", "Criar conta"))


@router.post("/api/signup")
def signup(payload: SignupRequest, request: Request, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Já existe uma conta com este e-mail.")
    existing_users = db.query(User.id).first()
    is_admin = not existing_users or payload.email.lower() in settings.admin_emails
    user = User(
        name=payload.name.strip(),
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    ensure_default_subjects(user.id, db)
    request.session["user_id"] = user.id
    return {"message": "Conta criada com segurança.", "redirect": "/onboarding"}


@router.post("/api/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="E-mail ou senha inválidos.")
    request.session["user_id"] = user.id
    return {"message": "Entrada realizada.", "redirect": "/app/dashboard"}


@router.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"message": "Sessão encerrada.", "redirect": "/"}


@router.get("/onboarding")
def onboarding_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return login_redirect()
    return templates.TemplateResponse(request, "onboarding.html", app_context(request, user, "onboarding", "Configuração inicial"))


@router.post("/api/onboarding")
def onboarding(payload: OnboardingRequest, current_user: User = Depends(require_api_user), db: Session = Depends(get_db)):
    if payload.name:
        current_user.name = payload.name.strip()
    current_user.age = payload.age

    overload_risk = _estimate_overload(payload)
    summary = _build_profile_summary(payload, overload_risk)
    profile = current_user.profile or UserProfile(user_id=current_user.id)
    profile.school_year = payload.school_year
    profile.routine_type = payload.routine_type
    profile.target_course = payload.target_course
    profile.target_universities = payload.target_universities
    profile.target_exams = payload.target_exams
    profile.main_difficulty = payload.main_difficulty
    profile.weekly_priority = payload.weekly_priority
    profile.overload_risk = overload_risk
    profile.study_profile_summary = summary
    db.add(profile)
    include_technical = "técnico" in " ".join([payload.school_year or "", payload.routine_type or ""]).lower()
    ensure_default_subjects(current_user.id, db, include_technical=include_technical)
    created_blocks = persist_onboarding_routine(current_user.id, payload, db)
    db.commit()

    plan = _build_initial_seven_day_plan(payload)
    return {
        "message": "Perfil criado. Seu plano inicial está pronto para ajustes.",
        "profile": {
            "perfil_do_estudante": summary,
            "gargalo_principal": payload.main_difficulty or "ainda não informado",
            "risco_de_sobrecarga": overload_risk,
            "prioridade_da_primeira_semana": payload.weekly_priority,
            "primeiras_recomendacoes": [
                "Cadastre as pendências mais urgentes antes de adicionar materiais extras.",
                "Reserve revisões curtas para flashcards e erros de simulado.",
                "Não tente recuperar tudo em um único dia.",
            ],
            "plano_inicial_7_dias": plan,
            "blocos_de_rotina_salvos": created_blocks,
        },
        "redirect": "/app/dashboard",
    }


def _estimate_overload(payload: OnboardingRequest) -> str:
    text = " ".join([payload.free_hours_per_day or "", payload.main_difficulty or "", payload.routine_type or ""]).lower()
    if "falta de tempo" in text or "trabalho" in text or "estágio" in text or "1" in text:
        return "alto"
    if "2" in text or "3" in text or "ansiedade" in text:
        return "moderado"
    return "baixo"


def _build_profile_summary(payload: OnboardingRequest, overload_risk: str) -> str:
    parts = [
        payload.school_year or "situação escolar não informada",
        payload.routine_type or "rotina ainda incompleta",
        f"foco em {payload.target_exams or 'vestibulares ainda não definidos'}",
        f"prioridade inicial: {payload.weekly_priority}",
        f"risco de sobrecarga: {overload_risk}",
    ]
    return "Estudante com " + ", ".join(parts) + "."


def _build_initial_seven_day_plan(payload: OnboardingRequest) -> list[dict[str, str]]:
    subjects = [item.strip() for item in (payload.weak_subjects or "").split(",") if item.strip()]
    default_subjects = subjects or ["matéria mais urgente", "revisão de base", "redação"]
    today = date.today()
    return [
        {
            "dia": (today + timedelta(days=index)).isoformat(),
            "foco": default_subjects[index % len(default_subjects)],
            "ação": "bloco curto de estudo ativo + revisão de 10 minutos",
        }
        for index in range(7)
    ]
