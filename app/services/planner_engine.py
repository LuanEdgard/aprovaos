from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AIPlan, RoutineBlock, StudyTask
from app.services.ai_gateway import AIGateway
from app.services.ai_utils import truncate_text


PRIORITY_WEIGHTS = {"alta": 3, "média": 2, "baixa": 1}
SOURCE_WEIGHTS = {
    "Escola": {"school": 3, "escola": 3, "course": 1, "cursinho": 1, "vestibular": 1, "enem": 1},
    "Vestibular": {"vestibular": 3, "enem": 3, "course": 2, "cursinho": 2, "school": 1, "escola": 1},
    "Equilíbrio": {"school": 2, "escola": 2, "course": 2, "cursinho": 2, "vestibular": 2, "enem": 2, "personal": 2},
    "Recuperação": {"school": 2, "escola": 2, "course": 2, "cursinho": 2, "vestibular": 2, "enem": 2, "personal": 2, "revisão": 3},
}
ACTIVE_TASK_STATUSES = ["pending", "late", "rescheduled", "pendente", "atrasada", "reagendada"]


def _get_db(db: Session | None) -> tuple[Session, bool]:
    if db:
        return db, False
    return SessionLocal(), True


def calculate_available_study_windows(user_id: int, db: Session | None = None) -> list[dict[str, object]]:
    db, owns_session = _get_db(db)
    try:
        blocks = db.query(RoutineBlock).filter(RoutineBlock.user_id == user_id).all()
        busy_by_day: dict[int, list[tuple[time, time]]] = {day: [] for day in range(7)}
        for block in blocks:
            block_type = block.type or block.block_type
            if block_type in {"school", "course", "work", "transport", "sleep", "rest", "personal", "escola", "cursinho", "trabalho", "transporte", "sono", "descanso", "pessoal"}:
                weekday = block.day_of_week if block.day_of_week is not None else block.weekday
                busy_by_day[weekday].append((block.start_time, block.end_time))

        windows = []
        day_start = time(7, 0)
        day_end = time(22, 30)
        for weekday in range(7):
            busy = sorted(busy_by_day[weekday], key=lambda item: item[0])
            cursor = day_start
            for start, end in busy:
                gap = _minutes_between(cursor, start)
                if gap >= 45:
                    windows.append({"weekday": weekday, "start_time": cursor.isoformat(timespec="minutes"), "end_time": start.isoformat(timespec="minutes"), "minutes": gap})
                if end > cursor:
                    cursor = end
            gap = _minutes_between(cursor, day_end)
            if gap >= 45:
                windows.append({"weekday": weekday, "start_time": cursor.isoformat(timespec="minutes"), "end_time": day_end.isoformat(timespec="minutes"), "minutes": gap})
        return windows[:18]
    finally:
        if owns_session:
            db.close()


def _minutes_between(start: time, end: time) -> int:
    base = date.today()
    start_dt = datetime.combine(base, start)
    end_dt = datetime.combine(base, end)
    return max(0, int((end_dt - start_dt).total_seconds() // 60))


def prioritize_tasks(tasks: list[StudyTask], weekly_priority: str) -> list[StudyTask]:
    weights = SOURCE_WEIGHTS.get(weekly_priority, SOURCE_WEIGHTS["Equilíbrio"])
    today = date.today()

    def score(task: StudyTask) -> tuple[int, date]:
        urgency = 0
        deadline = task.due_date or task.deadline
        if deadline:
            days = (deadline - today).days
            urgency = 5 if days < 0 else max(0, 4 - days)
        source_key = (task.source or task.source_type or "").lower()
        category_bonus = 1 if task.task_category in {"flashcard_review", "material_review", "correction_review"} else 0
        return (
            PRIORITY_WEIGHTS.get(task.priority, 1) + weights.get(source_key, 1) + urgency + category_bonus,
            deadline or today + timedelta(days=30),
        )

    return sorted(tasks, key=score, reverse=True)


def generate_weekly_plan(user_id: int, weekly_priority: str, db: Session | None = None) -> AIPlan:
    db, owns_session = _get_db(db)
    try:
        pending = (
            db.query(StudyTask)
            .filter(StudyTask.user_id == user_id, StudyTask.status.in_(ACTIVE_TASK_STATUSES))
            .all()
        )
        ordered = prioritize_tasks(pending, weekly_priority)[:10]
        overload = detect_overload(user_id, db)
        task_lines = []
        for index, task in enumerate(ordered[:7], start=1):
            task_lines.append(f"{index}. {task.title} ({task.estimated_minutes} min, {task.priority})")
        if not task_lines:
            task_lines.append("1. Cadastre sua rotina e suas primeiras pendências para montar um plano mais preciso.")

        ai_plan_text = ""
        ai_rationale = ""
        if db:
            windows = calculate_available_study_windows(user_id, db)[:10]
            prompt = f"""
            Prioridade semanal escolhida: {weekly_priority}
            Risco de sobrecarga detectado: {overload}

            Pendências priorizadas:
            {chr(10).join(task_lines)}

            Janelas livres estimadas:
            {windows}

            Gere um plano de 7 dias realista para execução. Preserve descanso, evite empilhar atrasos e explique o critério.
            """
            response = AIGateway(db, user_id).plan_week(
                "Você monta planos semanais do AprovaOS. "
                "A resposta deve organizar, priorizar e adaptar a rotina sem prometer aprovação e sem virar curso. "
                "JSON esperado: {\"plan_text\": string, \"rationale\": string}.",
                prompt,
                max_tokens=1500,
            )
            if response.used_ai and isinstance(response.data, dict):
                ai_plan_text = truncate_text(str(response.data.get("plan_text") or ""), 2400)
                ai_rationale = truncate_text(str(response.data.get("rationale") or ""), 700)

        rationale = (
            "Plano reduzido para recuperação e manutenção de descanso."
            if overload["level"] == "alto"
            else "Plano montado por prazo, prioridade e foco semanal."
        )
        plan = AIPlan(
            user_id=user_id,
            week_start=date.today() - timedelta(days=date.today().weekday()),
            weekly_priority=weekly_priority,
            plan_text=ai_plan_text or "\n".join(task_lines),
            rationale=ai_rationale or rationale,
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)
        return plan
    finally:
        if owns_session:
            db.close()


def reschedule_missed_tasks(user_id: int, mode: str, db: Session | None = None) -> dict[str, object]:
    db, owns_session = _get_db(db)
    try:
        today = date.today()
        tasks = (
            db.query(StudyTask)
            .filter(StudyTask.user_id == user_id, StudyTask.status.in_(["pending", "late", "pendente", "atrasada"]))
            .order_by(StudyTask.due_date.asc().nulls_last(), StudyTask.deadline.asc().nulls_last())
            .all()
        )
        moved = 0
        for index, task in enumerate(prioritize_tasks(tasks, mode)[:8]):
            deadline = task.due_date or task.deadline
            if deadline and deadline < today:
                new_deadline = today + timedelta(days=min(index + 1, 7))
                task.deadline = new_deadline
                task.due_date = new_deadline
                task.status = "rescheduled"
                moved += 1
        ai_note = AIGateway(db, user_id).generate_text(
            "recovery",
            "reschedule_missed_tasks",
            "Explique uma reorganização de pendências atrasadas no AprovaOS com tom prático, sem culpa e sem prometer resultado.",
            f"Modo: {mode}. Pendências analisadas: {[{'titulo': task.title, 'categoria': task.task_category, 'fonte': task.source or task.source_type, 'prazo': str(task.due_date or task.deadline), 'minutos': task.estimated_minutes} for task in tasks[:12]]}. Tarefas reagendadas: {moved}.",
            max_tokens=500,
        )
        db.commit()
        return {
            "message": ai_note.text if ai_note.used_ai else "Sua semana foi reorganizada com prioridade para recuperar atrasos sem empilhar tudo em um dia.",
            "rescheduled": moved,
        }
    finally:
        if owns_session:
            db.close()


def preview_reschedule_missed_tasks(user_id: int, mode: str, db: Session | None = None) -> dict[str, object]:
    db, owns_session = _get_db(db)
    try:
        today = date.today()
        tasks = (
            db.query(StudyTask)
            .filter(StudyTask.user_id == user_id, StudyTask.status.in_(["pending", "late", "pendente", "atrasada"]))
            .order_by(StudyTask.due_date.asc().nulls_last(), StudyTask.deadline.asc().nulls_last())
            .all()
        )
        overdue = [task for task in tasks if (task.due_date or task.deadline) and (task.due_date or task.deadline) < today]
        if not overdue:
            return {"message": "Não há pendências atrasadas para reorganizar.", "preview": [], "windows": []}

        windows = _build_windows_by_date(calculate_available_study_windows(user_id, db), today, 14)
        sorted_tasks = prioritize_tasks(overdue, mode)
        preview: list[dict[str, object]] = []
        for index, task in enumerate(sorted_tasks[:20]):
            assigned_date, window = _pick_window_for_task(task, windows)
            if not assigned_date:
                assigned_date = today + timedelta(days=min(index + 1, 10))
            preview.append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "old_deadline": (task.due_date or task.deadline).isoformat() if (task.due_date or task.deadline) else None,
                    "new_deadline": assigned_date.isoformat(),
                    "window": window,
                    "priority": task.priority,
                    "estimated_minutes": task.estimated_minutes,
                }
            )
        return {
            "message": "Preview de reorganização gerado. Revise antes de confirmar.",
            "preview": preview,
            "windows": windows,
        }
    finally:
        if owns_session:
            db.close()


def confirm_reschedule_plan(user_id: int, preview: list[dict[str, object]], db: Session | None = None) -> dict[str, object]:
    db, owns_session = _get_db(db)
    try:
        if not preview:
            return {"message": "Nenhuma alteração para salvar.", "rescheduled": 0}
        by_id = {int(item["task_id"]): item for item in preview if str(item.get("task_id", "")).isdigit()}
        tasks = db.query(StudyTask).filter(StudyTask.user_id == user_id, StudyTask.id.in_(list(by_id.keys()))).all()
        moved = 0
        for task in tasks:
            target = by_id.get(task.id)
            if not target:
                continue
            try:
                new_deadline = date.fromisoformat(str(target.get("new_deadline")))
            except (TypeError, ValueError):
                continue
            task.deadline = new_deadline
            task.due_date = new_deadline
            task.status = "rescheduled"
            moved += 1
        db.commit()
        return {"message": f"{moved} pendências reagendadas com sucesso.", "rescheduled": moved}
    finally:
        if owns_session:
            db.close()


def detect_overload(user_id: int, db: Session | None = None) -> dict[str, object]:
    db, owns_session = _get_db(db)
    try:
        today = date.today()
        next_week = today + timedelta(days=7)
        tasks = (
            db.query(StudyTask)
            .filter(StudyTask.user_id == user_id, StudyTask.status.in_(ACTIVE_TASK_STATUSES))
            .filter((StudyTask.due_date == None) | (StudyTask.due_date <= next_week))  # noqa: E711
            .all()
        )
        planned_minutes = sum(task.estimated_minutes or 0 for task in tasks)
        overdue = sum(1 for task in tasks if (task.due_date or task.deadline) and (task.due_date or task.deadline) < today)
        level = "baixo"
        if planned_minutes > 1200 or overdue >= 5:
            level = "alto"
        elif planned_minutes > 720 or overdue >= 2:
            level = "moderado"
        return {
            "level": level,
            "planned_minutes": planned_minutes,
            "overdue_count": overdue,
            "warning": "Há risco de sobrecarga. Reduza tarefas não essenciais e mantenha descanso." if level == "alto" else "Carga administrável para a semana.",
        }
    finally:
        if owns_session:
            db.close()


def _build_windows_by_date(windows: list[dict[str, object]], start_day: date, horizon_days: int) -> list[dict[str, object]]:
    indexed: list[dict[str, object]] = []
    for offset in range(horizon_days):
        day = start_day + timedelta(days=offset)
        weekday = day.weekday()
        for item in windows:
            if int(item.get("weekday", -1)) != weekday:
                continue
            indexed.append(
                {
                    "date": day.isoformat(),
                    "weekday": weekday,
                    "start_time": item.get("start_time"),
                    "end_time": item.get("end_time"),
                    "minutes": int(item.get("minutes") or 0),
                    "remaining_minutes": int(item.get("minutes") or 0),
                }
            )
    return indexed


def _pick_window_for_task(task: StudyTask, windows: list[dict[str, object]]) -> tuple[date | None, dict[str, object] | None]:
    needed = int(task.estimated_minutes or 50)
    for item in windows:
        if int(item.get("remaining_minutes") or 0) < min(needed, 120):
            continue
        item["remaining_minutes"] = int(item.get("remaining_minutes") or 0) - min(needed, 120)
        return date.fromisoformat(str(item["date"])), {
            "date": item["date"],
            "start_time": item.get("start_time"),
            "end_time": item.get("end_time"),
        }
    return None, None
