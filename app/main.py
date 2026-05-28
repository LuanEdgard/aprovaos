from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import init_db
from app.routers import ai, ai_settings, auth, dashboard, essays, exams, flashcards, materials, planner, reports, routine, subjects, tutor


app = FastAPI(title=settings.app_name)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie,
    https_only=False,
    same_site="lax",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(dashboard.router)
app.include_router(auth.router)
app.include_router(routine.router)
app.include_router(subjects.router)
app.include_router(materials.router)
app.include_router(flashcards.router)
app.include_router(exams.router)
app.include_router(essays.router)
app.include_router(planner.router)
app.include_router(tutor.router)
app.include_router(ai.router)
app.include_router(reports.router)
app.include_router(ai_settings.router)


@app.on_event("startup")
def startup() -> None:
    init_db()


# TODO: antes de produção, adicionar proteção CSRF para formulários autenticados,
# rotação de chave de sessão, HTTPS obrigatório e política de retenção de dados.
