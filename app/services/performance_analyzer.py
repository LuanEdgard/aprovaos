from collections import Counter

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Essay, ExamResult, Flashcard, StudyTask
from app.services.ai_gateway import AIGateway
from app.services.ai_utils import truncate_text


def _get_db(db: Session | None) -> tuple[Session, bool]:
    if db:
        return db, False
    return SessionLocal(), True


def analyze_exam_results(user_id: int, db: Session | None = None) -> dict[str, object]:
    db, owns_session = _get_db(db)
    try:
        exams = db.query(ExamResult).filter(ExamResult.user_id == user_id).order_by(ExamResult.date.asc()).all()
        if not exams:
            return {"has_data": False, "message": "Registre um simulado para acompanhar evolução por área."}
        latest = exams[-1]
        areas = {
            "Linguagens": latest.score_languages,
            "Humanas": latest.score_human_sciences,
            "Natureza": latest.score_natural_sciences,
            "Matemática": latest.score_math,
        }
        valid = {key: value for key, value in areas.items() if value is not None}
        weakest = min(valid.items(), key=lambda item: item[1])[0] if valid else "não identificado"
        strongest = max(valid.items(), key=lambda item: item[1])[0] if valid else "não identificado"
        reasons = Counter(exam.error_reason for exam in exams if exam.error_reason)
        return {
            "has_data": True,
            "count": len(exams),
            "latest_score": latest.total_score,
            "weakest_area": weakest,
            "strongest_area": strongest,
            "error_reasons": dict(reasons),
            "series": [{"date": exam.date.isoformat(), "score": exam.total_score or 0} for exam in exams],
        }
    finally:
        if owns_session:
            db.close()


def analyze_essay_progress(user_id: int, db: Session | None = None) -> dict[str, object]:
    db, owns_session = _get_db(db)
    try:
        essays = db.query(Essay).filter(Essay.user_id == user_id).order_by(Essay.date.asc()).all()
        if not essays:
            return {"has_data": False, "message": "Registre redações para acompanhar evolução por competência."}
        latest = essays[-1]
        scores = [essay.total_score for essay in essays if essay.total_score is not None]
        average = round(sum(scores) / len(scores), 1) if scores else None
        competencies = {"C1": latest.c1, "C2": latest.c2, "C3": latest.c3, "C4": latest.c4, "C5": latest.c5}
        valid = {key: value for key, value in competencies.items() if value is not None}
        weakest = min(valid.items(), key=lambda item: item[1])[0] if valid else "não identificada"
        return {
            "has_data": True,
            "average": average,
            "latest_score": latest.total_score,
            "weakest_competence": weakest,
            "series": [{"date": essay.date.isoformat(), "score": essay.total_score or 0} for essay in essays],
        }
    finally:
        if owns_session:
            db.close()


def detect_weak_subjects(user_id: int, db: Session | None = None) -> list[str]:
    db, owns_session = _get_db(db)
    try:
        missed_tasks = (
            db.query(StudyTask.subject)
            .filter(StudyTask.user_id == user_id, StudyTask.status.in_(["late", "pending", "atrasada", "pendente"]))
            .all()
        )
        hard_cards = (
            db.query(Flashcard.subject)
            .filter(Flashcard.user_id == user_id, Flashcard.difficulty.in_(["Errei", "Difícil"]))
            .all()
        )
        subjects = [item[0] for item in missed_tasks + hard_cards if item[0]]
        return [subject for subject, _ in Counter(subjects).most_common(5)]
    finally:
        if owns_session:
            db.close()


def recommend_next_focus(user_id: int, db: Session | None = None) -> str:
    weak_subjects = detect_weak_subjects(user_id, db)
    if weak_subjects:
        return f"Comece por {weak_subjects[0]}, usando revisão ativa e questões curtas antes de avançar."
    exams = analyze_exam_results(user_id, db)
    if exams.get("has_data"):
        return f"Priorize {exams['weakest_area']} no próximo bloco de estudo."
    return "Cadastre pendências, simulados ou materiais para receber uma recomendação mais precisa."


def generate_performance_analysis(user_id: int, db: Session | None = None) -> dict[str, object]:
    db, owns_session = _get_db(db)
    try:
        exams = analyze_exam_results(user_id, db)
        essays = analyze_essay_progress(user_id, db)
        weak_subjects = detect_weak_subjects(user_id, db)
        if not exams.get("has_data") and not essays.get("has_data") and not weak_subjects:
            return {"has_data": False, "analysis_text": "Registre simulados, redações ou revisões para eu analisar seu desempenho com mais precisão.", "used_ai": False}

        fallback_lines = ["Análise dos seus registros:"]
        if exams.get("has_data"):
            fallback_lines.append(f"- Simulados: área mais fraca agora é {exams['weakest_area']}; área mais forte é {exams['strongest_area']}.")
        if essays.get("has_data"):
            fallback_lines.append(f"- Redação: média estimada {essays['average']}; competência que pede atenção: {essays['weakest_competence']}.")
        if weak_subjects:
            fallback_lines.append(f"- Matérias com mais sinais de risco: {', '.join(weak_subjects[:3])}.")
        fallback_lines.append(f"Próximo foco recomendado: {recommend_next_focus(user_id, db)}")

        if db:
            latest_exams = db.query(ExamResult).filter(ExamResult.user_id == user_id).order_by(ExamResult.date.desc()).limit(5).all()
            latest_essays = db.query(Essay).filter(Essay.user_id == user_id).order_by(Essay.date.desc()).limit(5).all()
            prompt = f"""
            Resumo dos simulados: {exams}
            Resumo das redações: {essays}
            Matérias com risco: {weak_subjects}
            Simulados recentes:
            {[{"tipo": exam.exam_type, "data": exam.date.isoformat(), "nota": exam.total_score, "erros": truncate_text(exam.main_mistakes, 220), "motivo": exam.error_reason} for exam in latest_exams]}
            Redações recentes:
            {[{"tema": essay.theme, "data": essay.date.isoformat(), "nota": essay.total_score, "c1": essay.c1, "c2": essay.c2, "c3": essay.c3, "c4": essay.c4, "c5": essay.c5, "erros": truncate_text(essay.recurring_errors, 220)} for essay in latest_essays]}
            """
            response = AIGateway(db, user_id).generate_text(
                "reports",
                "performance_analysis",
                "Analise desempenho no AprovaOS com base em simulados, redações e sinais de revisão. "
                "Use termos como estimativa, tendência e registro de evolução. Não faça correção oficial de redação. "
                "Entregue uma análise curta, prática e com foco recomendado para a próxima semana.",
                prompt,
                max_tokens=1200,
            )
            if response.used_ai and response.text:
                return {"has_data": True, "analysis_text": response.text, "used_ai": True}

        return {"has_data": True, "analysis_text": "\n".join(fallback_lines), "used_ai": False}
    finally:
        if owns_session:
            db.close()
