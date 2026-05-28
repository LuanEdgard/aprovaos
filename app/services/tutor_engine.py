from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import CalendarEvent, Essay, ExamResult, Flashcard, Material, RoutineBlock, StudyTask, User
from app.services.ai_service import build_user_context, generate_response
from app.services.ai_context_builder import build_student_context
from app.services.ai_gateway import AIGateway
from app.services.ai_utils import as_list, truncate_text
from app.services.flashcard_engine import generate_flashcards_from_text, get_due_flashcards
from app.services.performance_analyzer import generate_performance_analysis, recommend_next_focus
from app.services.planner_engine import detect_overload, generate_weekly_plan, prioritize_tasks


NO_DATA_MESSAGE = "Eu ainda preciso de mais dados seus para responder com precisão. Cadastre sua rotina, materiais ou simulados para eu conseguir te orientar melhor."
DISTRESS_TERMS = ["me matar", "não aguento", "sumir", "desistir de viver", "quero morrer", "não quero viver"]


def _get_db(db: Session | None) -> tuple[Session, bool]:
    if db:
        return db, False
    return SessionLocal(), True


def handle_tutor_message(user_id: int, message: str, mode: str, db: Session | None = None) -> dict[str, object]:
    db, owns_session = _get_db(db)
    try:
        normalized = (message or "").lower()
        if any(term in normalized for term in DISTRESS_TERMS):
            return {
                "reply": (
                    "Sinto muito que você esteja passando por isso. Eu posso ajudar a organizar seus estudos, "
                    "mas esse tipo de sofrimento merece apoio humano agora: fale com um adulto de confiança, "
                    "familiar, orientador da escola ou profissional qualificado. Se houver risco imediato, procure ajuda presencial ou serviço de emergência."
                ),
                "sources": [],
                "used_ai": False,
            }

        modes = {
            "Organizador": organize_week_response,
            "Organizer": organize_week_response,
            "organizer": organize_week_response,
            "Analista": analyze_performance_response,
            "Analyst": analyze_performance_response,
            "analyst": analyze_performance_response,
            "Tutor com fontes": answer_with_sources,
            "Tutor with sources": answer_with_sources,
            "tutor with sources": answer_with_sources,
            "Criador de flashcards": create_flashcards_response,
            "Flashcard creator": create_flashcards_response,
            "flashcard creator": create_flashcards_response,
            "Recuperação": recovery_plan_response,
            "Recovery": recovery_plan_response,
            "recovery": recovery_plan_response,
            "Prioritizer": prioritizer_response,
            "prioritizer": prioritizer_response,
        }
        handler = modes.get(mode, organize_week_response)
        return handler(user_id, message, db)
    finally:
        if owns_session:
            db.close()


def _has_any_data(user_id: int, db: Session) -> bool:
    checks = [
        db.query(StudyTask).filter(StudyTask.user_id == user_id).first(),
        db.query(RoutineBlock).filter(RoutineBlock.user_id == user_id).first(),
        db.query(Material).filter(Material.user_id == user_id).first(),
        db.query(Flashcard).filter(Flashcard.user_id == user_id).first(),
        db.query(ExamResult).filter(ExamResult.user_id == user_id).first(),
        db.query(Essay).filter(Essay.user_id == user_id).first(),
        db.query(CalendarEvent).filter(CalendarEvent.user_id == user_id).first(),
    ]
    return any(checks)


def organize_week_response(user_id: int, message: str = "", db: Session | None = None) -> dict[str, object]:
    db, owns_session = _get_db(db)
    try:
        has_data = _has_any_data(user_id, db)
        user = db.get(User, user_id)
        context = build_student_context(user, db) if user else _student_context(user_id, db)
        response = AIGateway(db, user_id).tutor_chat(
            "Modo Organizador. Decida o que o estudante deve estudar hoje e como organizar a semana. "
            "Priorize execução, prazos, revisão ativa e carga realista. Não transforme em curso. "
            "Se o estudante ainda não tiver dados cadastrados, responda como onboarding assistido: faça um plano inicial simples "
            "e peça somente as próximas informações necessárias.",
            _context_prompt(context, message),
            max_tokens=1400,
        )
        if response.used_ai and response.text:
            return {"reply": response.text, "sources": [], "used_ai": True}
        local = generate_response(user_id, "organizer", message, context, db)
        if local.get("text"):
            return {"reply": str(local["text"]), "sources": [], "used_ai": bool(local.get("used_ai"))}
        if not has_data:
            return {"reply": NO_DATA_MESSAGE, "sources": [], "used_ai": False}

        tasks = db.query(StudyTask).filter(StudyTask.user_id == user_id, StudyTask.status != "concluída").all()
        ordered = prioritize_tasks(tasks, "Equilíbrio")[:5]
        overload = detect_overload(user_id, db)
        lines = ["Para hoje, eu priorizaria:"]
        for task in ordered:
            lines.append(f"- {task.title} ({task.estimated_minutes} min, fonte: {task.source_type})")
        lines.append(f"Carga da semana: {overload['level']}. {overload['warning']}")
        lines.append("Se o dia apertar, preserve a primeira tarefa e uma revisão curta. O restante pode ser reagendado.")
        return {"reply": "\n".join(lines), "sources": [], "used_ai": False}
    finally:
        if owns_session:
            db.close()


def analyze_performance_response(user_id: int, message: str = "", db: Session | None = None) -> dict[str, object]:
    db, owns_session = _get_db(db)
    try:
        analysis = generate_performance_analysis(user_id, db)
        if not analysis.get("has_data"):
            local = generate_response(user_id, "analyst", message, build_user_context(user_id, db), db)
            return {"reply": str(local.get("text") or NO_DATA_MESSAGE), "sources": [], "used_ai": bool(local.get("used_ai"))}
        return {"reply": analysis["analysis_text"], "sources": [], "used_ai": bool(analysis.get("used_ai"))}
    finally:
        if owns_session:
            db.close()


def answer_with_sources(user_id: int, message: str, db: Session | None = None) -> dict[str, object]:
    db, owns_session = _get_db(db)
    try:
        materials = (
            db.query(Material)
            .filter(Material.user_id == user_id)
            .filter(Material.extracted_text.isnot(None))
            .order_by(Material.created_at.desc())
            .limit(12)
            .all()
        )

        if not materials:
            response = AIGateway(db, user_id).tutor_chat(
                "Modo Tutor com fontes, mas o estudante ainda não tem material enviado. "
                "Responda de forma geral e deixe claro que não é baseado em arquivos enviados.",
                f"Pergunta do estudante: {message}",
                max_tokens=900,
            )
            if response.used_ai and response.text:
                return {
                    "reply": f"Resposta geral, não baseada em arquivos enviados:\n{response.text}",
                    "sources": [],
                    "used_ai": True,
                }
            return {
                "reply": (
                    "Resposta geral, não baseada em material enviado: para estudar esse ponto, comece identificando o conceito central, "
                    "faça 3 perguntas de recuperação ativa e resolva questões curtas. Envie materiais para eu responder com fontes específicas."
                ),
                "sources": [],
                "used_ai": False,
            }

        source_blocks = _select_material_sources(materials, message)
        prompt = f"""
        Pergunta do estudante:
        {message}

        Fontes disponíveis:
        {json.dumps(source_blocks, ensure_ascii=False, indent=2)}

        Responda somente com base nas fontes quando elas forem suficientes.
        Cite no texto o título e a seção no formato: Fonte: título — seção.
        Se as fontes não cobrirem a pergunta, diga claramente o limite e dê apenas orientação geral de estudo.
        """
        response = AIGateway(db, user_id).tutor_chat(
            "Modo Tutor com fontes. Responda com base em materiais enviados, citando título e seção quando possível. "
            "Não invente fonte, não diga que é correção oficial, não prometa resultado.",
            prompt,
            max_tokens=1300,
        )
        if response.used_ai and response.text:
            return {
                "reply": response.text,
                "sources": [f"{item['title']} — {item['section']}" for item in source_blocks],
                "used_ai": True,
            }

        first = source_blocks[0]
        return {
            "reply": (
                f"Com base no material \"{first['title']}\" — {first['section']}, o trecho mais útil é: "
                f"{first['excerpt']}\n\nUse isso como base para responder com suas palavras e transformar em perguntas de revisão ativa."
            ),
            "sources": [f"{item['title']} — {item['section']}" for item in source_blocks],
            "used_ai": False,
        }
    finally:
        if owns_session:
            db.close()


def create_flashcards_response(user_id: int, message: str, db: Session | None = None) -> dict[str, object]:
    db, owns_session = _get_db(db)
    try:
        material = db.query(Material).filter(Material.user_id == user_id).order_by(Material.created_at.desc()).first()
        text = (material.extracted_text if material else "") or message
        if not text.strip():
            return {"reply": NO_DATA_MESSAGE, "sources": [], "used_ai": False}

        prompt = f"""
        Fonte: {material.title if material else "texto enviado na conversa"}
        Texto:
        {truncate_text(text, 8000)}

        Gere até 6 flashcards objetivos para revisão ativa.
        """
        response = AIGateway(db, user_id).generate_json(
            "flashcards",
            "tutor_flashcard_suggestions",
            "Modo Criador de flashcards. Gere perguntas e respostas curtas para repetição espaçada. "
            "Não transforme em aula. JSON esperado: {\"flashcards\": [{\"topic\": string, \"front\": string, \"back\": string}]}",
            prompt,
            max_tokens=1200,
        )
        cards = _cards_from_ai_data(response.data)
        if response.used_ai and cards:
            return {"reply": _format_card_suggestions(cards), "sources": [material.title] if material else [], "used_ai": True}

        cards = generate_flashcards_from_text(text)
        if not cards:
            local = generate_response(user_id, "flashcard creator", message, build_user_context(user_id, db), db)
            return {"reply": str(local.get("text") or NO_DATA_MESSAGE), "sources": [], "used_ai": bool(local.get("used_ai"))}
        return {"reply": _format_card_suggestions(cards[:5]), "sources": [material.title] if material else [], "used_ai": False}
    finally:
        if owns_session:
            db.close()


def recovery_plan_response(user_id: int, message: str = "", db: Session | None = None) -> dict[str, object]:
    db, owns_session = _get_db(db)
    try:
        has_data = _has_any_data(user_id, db)
        user = db.get(User, user_id)
        context = build_student_context(user, db) if user else _student_context(user_id, db)
        response = AIGateway(db, user_id).generate_text(
            "recovery",
            "recovery_plan",
            "Modo Recuperação. Ajude o estudante a recuperar atraso sem culpa e sem sobrecarga. "
            "Corte tarefas não essenciais, preserve descanso e defina próximos passos concretos. "
            "Se ainda não houver dados cadastrados, monte um plano inicial enxuto e peça os dados mínimos para refinar.",
            _context_prompt(context, message),
            max_tokens=1300,
        )
        if response.used_ai and response.text:
            return {"reply": response.text, "sources": [], "used_ai": True}
        local = generate_response(user_id, "recovery", message, context, db)
        if local.get("text"):
            return {"reply": str(local["text"]), "sources": [], "used_ai": bool(local.get("used_ai"))}
        if not has_data:
            return {"reply": NO_DATA_MESSAGE, "sources": [], "used_ai": False}

        plan = generate_weekly_plan(user_id, "Recuperação", db)
        return {
            "reply": (
                f"Plano de recuperação sem sobrecarga:\n{plan.plan_text}\n\n"
                f"Critério: {plan.rationale} Não tente compensar tudo de uma vez; recupere o essencial primeiro."
            ),
            "sources": [],
            "used_ai": False,
        }
    finally:
        if owns_session:
            db.close()


def prioritizer_response(user_id: int, message: str = "", db: Session | None = None) -> dict[str, object]:
    db, owns_session = _get_db(db)
    try:
        local = generate_response(user_id, "prioritizer", message, build_user_context(user_id, db), db)
        return {"reply": str(local.get("text") or NO_DATA_MESSAGE), "sources": [], "used_ai": bool(local.get("used_ai"))}
    finally:
        if owns_session:
            db.close()


def _student_context(user_id: int, db: Session) -> dict[str, Any]:
    today = date.today()
    tasks = (
        db.query(StudyTask)
        .filter(StudyTask.user_id == user_id, StudyTask.status.in_(["pendente", "atrasada", "reagendada"]))
        .order_by(StudyTask.deadline.asc().nulls_last(), StudyTask.created_at.desc())
        .limit(12)
        .all()
    )
    routines = db.query(RoutineBlock).filter(RoutineBlock.user_id == user_id).order_by(RoutineBlock.weekday, RoutineBlock.start_time).limit(16).all()
    materials = db.query(Material).filter(Material.user_id == user_id).order_by(Material.created_at.desc()).limit(6).all()
    flashcards = get_due_flashcards(user_id, db)[:8]
    exams = db.query(ExamResult).filter(ExamResult.user_id == user_id).order_by(ExamResult.date.desc()).limit(5).all()
    essays = db.query(Essay).filter(Essay.user_id == user_id).order_by(Essay.date.desc()).limit(5).all()
    events = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.user_id == user_id, CalendarEvent.status.in_(["pendente", "atrasada", "reagendada"]))
        .order_by(CalendarEvent.start_datetime.asc())
        .limit(8)
        .all()
    )
    return {
        "data_de_hoje": today.isoformat(),
        "sobrecarga": detect_overload(user_id, db),
        "foco_recomendado": recommend_next_focus(user_id, db),
        "tarefas": [_task_context(task) for task in tasks],
        "rotina": [_routine_context(block) for block in routines],
        "materiais": [_material_context(material) for material in materials],
        "flashcards_para_revisar": [_flashcard_context(card) for card in flashcards],
        "simulados": [_exam_context(exam) for exam in exams],
        "redacoes": [_essay_context(essay) for essay in essays],
        "eventos": [_event_context(event) for event in events],
    }


def _context_prompt(context: dict[str, Any], message: str) -> str:
    return (
        f"Mensagem do estudante: {message or 'Sem mensagem adicional.'}\n\n"
        f"Contexto resumido do estudante no AprovaOS:\n{json.dumps(context, ensure_ascii=False, default=str, indent=2)}"
    )


def _task_context(task: StudyTask) -> dict[str, Any]:
    return {
        "titulo": task.title,
        "materia": task.subject,
        "fonte": task.source_type,
        "prioridade": task.priority,
        "status": task.status,
        "prazo": task.deadline.isoformat() if task.deadline else None,
        "minutos_estimados": task.estimated_minutes,
    }


def _routine_context(block: RoutineBlock) -> dict[str, Any]:
    return {
        "titulo": block.title,
        "tipo": block.block_type,
        "dia_da_semana": block.weekday,
        "inicio": block.start_time.isoformat(timespec="minutes"),
        "fim": block.end_time.isoformat(timespec="minutes"),
    }


def _material_context(material: Material) -> dict[str, Any]:
    return {
        "titulo": material.title,
        "tipo": material.material_type,
        "fonte": material.source_type,
        "materia": material.subject,
        "status": material.status,
        "resumo": truncate_text(material.summary or material.extracted_text, 500),
    }


def _flashcard_context(card: Flashcard) -> dict[str, Any]:
    return {
        "materia": card.subject,
        "topico": card.topic,
        "dificuldade": card.difficulty,
        "revisoes": card.review_count,
        "proxima_revisao": card.next_review_at.isoformat() if card.next_review_at else None,
    }


def _exam_context(exam: ExamResult) -> dict[str, Any]:
    return {
        "tipo": exam.exam_type,
        "data": exam.date.isoformat(),
        "nota_total": exam.total_score,
        "linguagens": exam.score_languages,
        "humanas": exam.score_human_sciences,
        "natureza": exam.score_natural_sciences,
        "matematica": exam.score_math,
        "redacao": exam.essay_score,
        "motivo_de_erro": exam.error_reason,
        "erros": truncate_text(exam.main_mistakes, 260),
    }


def _essay_context(essay: Essay) -> dict[str, Any]:
    return {
        "tema": essay.theme,
        "data": essay.date.isoformat(),
        "nota_total": essay.total_score,
        "c1": essay.c1,
        "c2": essay.c2,
        "c3": essay.c3,
        "c4": essay.c4,
        "c5": essay.c5,
        "erros_recorrentes": truncate_text(essay.recurring_errors, 260),
        "observacao": "registro de correção e estimativa de evolução, não correção oficial",
    }


def _event_context(event: CalendarEvent) -> dict[str, Any]:
    return {
        "titulo": event.title,
        "tipo": event.event_type,
        "inicio": event.start_datetime.isoformat(),
        "fim": event.end_datetime.isoformat() if event.end_datetime else None,
        "status": event.status,
    }


def _select_material_sources(materials: list[Material], message: str) -> list[dict[str, str]]:
    terms = [term for term in re.findall(r"\w+", (message or "").lower()) if len(term) > 3]

    def score(material: Material) -> int:
        haystack = f"{material.title} {material.subject or ''} {material.summary or ''} {material.extracted_text or ''}".lower()
        return sum(haystack.count(term) for term in terms)

    ranked = sorted(materials, key=score, reverse=True)
    sources = []
    for material in ranked[:3]:
        section, excerpt = _source_excerpt(material.extracted_text or material.summary or material.title, terms)
        sources.append({"title": material.title, "section": section, "excerpt": excerpt})
    return sources


def _source_excerpt(text: str, terms: list[str]) -> tuple[str, str]:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return "Trecho principal", ""
    match_index = 0
    for index, line in enumerate(lines):
        lower = line.lower()
        if any(term in lower for term in terms):
            match_index = index
            break
    section = "Trecho relevante"
    for previous in reversed(lines[: match_index + 1]):
        clean = previous.strip("#: ").strip()
        if 3 <= len(clean) <= 90 and not clean.endswith("."):
            section = clean
            break
    start = max(0, match_index - 1)
    end = min(len(lines), match_index + 3)
    excerpt = truncate_text(" ".join(lines[start:end]), 900)
    return section, excerpt


def _cards_from_ai_data(data: Any) -> list[dict[str, str]]:
    cards = []
    for item in as_list(data):
        if not isinstance(item, dict):
            continue
        front = truncate_text(str(item.get("front") or ""), 260)
        back = truncate_text(str(item.get("back") or ""), 700)
        if len(front) < 8 or len(back) < 8:
            continue
        cards.append({"topic": truncate_text(str(item.get("topic") or "Revisão ativa"), 120), "front": front, "back": back})
    return cards[:8]


def _format_card_suggestions(cards: list[dict[str, str]]) -> str:
    lines = ["Sugestões de flashcards:"]
    for card in cards:
        lines.append(f"- Frente: {card['front']}\n  Verso: {truncate_text(card['back'], 260)}")
    return "\n".join(lines)
