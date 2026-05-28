from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    CalendarEvent,
    Essay,
    ExamResult,
    Flashcard,
    Material,
    RoutineBlock,
    StudyTask,
    Subject,
    User,
)
from app.services.performance_analyzer import detect_weak_subjects
from app.services.planner_engine import calculate_available_study_windows, detect_overload


TASK_DONE_STATUSES = {"completed", "concluída"}
TASK_PENDING_STATUSES = {"pending", "late", "rescheduled", "pendente", "atrasada", "reagendada"}
EXAM_EVENT_TYPES = {"simulado", "prova", "simulation"}
ESSAY_EVENT_TYPES = {"redação", "essay"}


class AIContextService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def build_student_context(self, user_id: int) -> dict[str, Any]:
        user = self._safe_get_user(user_id)
        profile = getattr(user, "profile", None)
        today = date.today()

        tasks = self._safe_all(
            lambda: self.db.query(StudyTask)
            .filter(StudyTask.user_id == user_id)
            .order_by(StudyTask.due_date.asc().nulls_last(), StudyTask.deadline.asc().nulls_last(), StudyTask.created_at.desc())
            .all(),
            [],
        )
        routine_blocks = self._safe_all(
            lambda: self.db.query(RoutineBlock)
            .filter(RoutineBlock.user_id == user_id)
            .order_by(RoutineBlock.weekday.asc(), RoutineBlock.start_time.asc())
            .all(),
            [],
        )
        materials = self._safe_all(
            lambda: self.db.query(Material)
            .filter(Material.user_id == user_id)
            .order_by(Material.created_at.desc())
            .all(),
            [],
        )
        exams = self._safe_all(
            lambda: self.db.query(ExamResult)
            .filter(ExamResult.user_id == user_id)
            .order_by(ExamResult.date.desc())
            .all(),
            [],
        )
        essays = self._safe_all(
            lambda: self.db.query(Essay)
            .filter(Essay.user_id == user_id)
            .order_by(Essay.date.desc())
            .all(),
            [],
        )
        events = self._safe_all(
            lambda: self.db.query(CalendarEvent)
            .filter(CalendarEvent.user_id == user_id)
            .order_by(CalendarEvent.start_datetime.asc())
            .all(),
            [],
        )
        due_flashcards = self._safe_all(
            lambda: self.db.query(Flashcard)
            .filter(Flashcard.user_id == user_id)
            .filter((Flashcard.next_review_at.is_(None)) | (Flashcard.next_review_at <= datetime.now(timezone.utc)))
            .order_by(Flashcard.next_review_at.asc().nullsfirst())
            .all(),
            [],
        )

        today_tasks = [task for task in tasks if self._is_due_today(task, today) and self._is_pending(task)]
        overdue_tasks = [task for task in tasks if self._is_overdue(task, today) and self._is_pending(task)]
        next_exam_events = [event for event in events if (event.event_type or "").lower() in EXAM_EVENT_TYPES and event.start_datetime and event.start_datetime.date() >= today][:10]
        next_essay_events = [event for event in events if (event.event_type or "").lower() in ESSAY_EVENT_TYPES and event.start_datetime and event.start_datetime.date() >= today][:10]

        context = {
            "student": {
                "id": user_id,
                "name": getattr(user, "name", None),
                "age": getattr(user, "age", None),
                "school_year": getattr(profile, "school_year", None) if profile else None,
                "routine_type": getattr(profile, "routine_type", None) if profile else None,
                "weekly_priority": getattr(profile, "weekly_priority", None) if profile else None,
            },
            "goals": {
                "target_course": getattr(profile, "target_course", None) if profile else None,
                "target_universities": self._csv(getattr(profile, "target_universities", None)) if profile else [],
                "target_exams": self._csv(getattr(profile, "target_exams", None)) if profile else [],
                "vestibulares_alvo": self._csv(getattr(profile, "vestibulares_alvo", None)) if profile else [],
            },
            "routine": {
                "weekly_blocks": [self._routine_item(item) for item in routine_blocks[:50]],
                "study_windows": calculate_available_study_windows(user_id, self.db),
            },
            "today_tasks": [self._task_item(item) for item in today_tasks[:20]],
            "overdue_tasks": [self._task_item(item) for item in overdue_tasks[:20]],
            "upcoming_exam_events": [self._event_item(item) for item in next_exam_events],
            "upcoming_essay_events": [self._event_item(item) for item in next_essay_events],
            "recent_materials": [self._material_item(item) for item in materials[:20]],
            "due_flashcards": [self._flashcard_item(item) for item in due_flashcards[:30]],
            "subjects_with_more_delay": self._subjects_with_more_delay(overdue_tasks),
            "subjects_with_weaker_performance": detect_weak_subjects(user_id, self.db),
            "exam_history": [self._exam_item(item) for item in exams[:15]],
            "essay_history": [self._essay_item(item) for item in essays[:15]],
            "weekly_report": self._build_weekly_report_snapshot(tasks, exams, essays),
            "overload_risk": detect_overload(user_id, self.db),
            "counts": {
                "tasks": len(tasks),
                "today_tasks": len(today_tasks),
                "overdue_tasks": len(overdue_tasks),
                "materials": len(materials),
                "due_flashcards": len(due_flashcards),
                "simulados": len(exams),
                "redacoes": len(essays),
                "events": len(events),
            },
        }
        return context

    def used_context_summary(self, context: dict[str, Any]) -> dict[str, int]:
        counts = context.get("counts") or {}
        return {
            "tasks": int(counts.get("tasks") or 0),
            "materials": int(counts.get("materials") or 0),
            "simulados": int(counts.get("simulados") or 0),
            "redacoes": int(counts.get("redacoes") or 0),
        }

    def material_for_user(self, user_id: int, material_id: int | None) -> Material | None:
        if not material_id:
            return None
        return self._safe_one(
            lambda: self.db.query(Material).filter(Material.id == material_id, Material.user_id == user_id).first(),
            None,
        )

    def list_user_materials(self, user_id: int, limit: int = 80) -> list[dict[str, Any]]:
        rows = self._safe_all(
            lambda: self.db.query(Material)
            .filter(Material.user_id == user_id)
            .order_by(Material.created_at.desc())
            .limit(limit)
            .all(),
            [],
        )
        return [self._material_item(item) for item in rows]

    def subject_label(self, subject_id: int | None) -> str | None:
        if not subject_id:
            return None
        row = self._safe_one(
            lambda: self.db.query(Subject).filter(Subject.id == subject_id).first(),
            None,
        )
        return row.name if row else None

    def _build_weekly_report_snapshot(
        self,
        tasks: list[StudyTask],
        exams: list[ExamResult],
        essays: list[Essay],
    ) -> dict[str, Any]:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        completed = [task for task in tasks if (task.status or "").lower() in TASK_DONE_STATUSES]
        completed_week = [task for task in completed if task.completed_at and task.completed_at.date() >= week_start]
        planned_minutes = sum(task.estimated_minutes or 0 for task in tasks if not self._task_date(task) or self._task_date(task) >= week_start)
        completed_minutes = sum(task.estimated_minutes or 0 for task in completed_week)
        weak_subjects = self._subjects_with_more_delay(
            [task for task in tasks if self._is_pending(task) and self._is_overdue(task, today)]
        )
        return {
            "week_start": week_start.isoformat(),
            "completed_tasks": len(completed_week),
            "planned_minutes": planned_minutes,
            "completed_minutes": completed_minutes,
            "exam_count": len(exams),
            "essay_count": len(essays),
            "weak_subjects": weak_subjects,
        }

    def _subjects_with_more_delay(self, tasks: list[StudyTask]) -> list[dict[str, Any]]:
        counter = Counter()
        for task in tasks:
            subject_name = task.subject or (task.subject_ref.name if task.subject_ref else None) or "geral"
            counter[subject_name] += 1
        return [{"subject": name, "count": amount} for name, amount in counter.most_common(6)]

    def _task_date(self, task: StudyTask) -> date | None:
        return task.due_date or task.deadline

    def _is_overdue(self, task: StudyTask, today: date) -> bool:
        due = self._task_date(task)
        return bool(due and due < today)

    def _is_due_today(self, task: StudyTask, today: date) -> bool:
        due = self._task_date(task)
        return bool(due and due == today)

    def _is_pending(self, task: StudyTask) -> bool:
        return (task.status or "").lower() in TASK_PENDING_STATUSES

    def _safe_get_user(self, user_id: int) -> User | None:
        return self._safe_one(lambda: self.db.get(User, user_id), None)

    def _safe_one(self, getter, default):
        try:
            return getter()
        except SQLAlchemyError:
            return default

    def _safe_all(self, getter, default: list[Any]) -> list[Any]:
        try:
            return getter()
        except SQLAlchemyError:
            return default

    def _csv(self, value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in str(value).split(",") if item.strip()]

    def _routine_item(self, block: RoutineBlock) -> dict[str, Any]:
        return {
            "id": block.id,
            "title": block.title,
            "type": block.type or block.block_type,
            "weekday": block.day_of_week if block.day_of_week is not None else block.weekday,
            "start_time": block.start_time.isoformat(timespec="minutes"),
            "end_time": block.end_time.isoformat(timespec="minutes"),
        }

    def _task_item(self, task: StudyTask) -> dict[str, Any]:
        due = self._task_date(task)
        return {
            "id": task.id,
            "title": task.title,
            "description": task.description or task.ai_description,
            "subject": task.subject or (task.subject_ref.name if task.subject_ref else None),
            "priority": task.priority,
            "status": task.status,
            "estimated_minutes": task.estimated_minutes,
            "deadline": due.isoformat() if due else None,
            "task_category": task.task_category,
        }

    def _event_item(self, event: CalendarEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "title": event.title,
            "type": event.event_type,
            "start_datetime": event.start_datetime.isoformat() if event.start_datetime else None,
            "end_datetime": event.end_datetime.isoformat() if event.end_datetime else None,
            "status": event.status,
        }

    def _material_item(self, material: Material) -> dict[str, Any]:
        return {
            "id": material.id,
            "title": material.title,
            "type": material.type or material.material_type,
            "subject": material.subject or (material.subject_ref.name if material.subject_ref else None),
            "topic": material.topic,
            "subtopic": material.subtopic,
            "summary": material.ai_summary or material.summary,
            "created_at": material.created_at.isoformat() if material.created_at else None,
        }

    def _flashcard_item(self, card: Flashcard) -> dict[str, Any]:
        return {
            "id": card.id,
            "subject": card.subject,
            "topic": card.topic,
            "front": card.front,
            "difficulty": card.difficulty,
            "review_count": card.review_count,
            "next_review_at": card.next_review_at.isoformat() if card.next_review_at else None,
        }

    def _exam_item(self, exam: ExamResult) -> dict[str, Any]:
        return {
            "id": exam.id,
            "type": exam.exam_type,
            "date": exam.date.isoformat() if exam.date else None,
            "total_score": exam.total_score,
            "score_math": exam.score_math,
            "score_languages": exam.score_languages,
            "score_human_sciences": exam.score_human_sciences,
            "score_natural_sciences": exam.score_natural_sciences,
            "essay_score": exam.essay_score,
            "error_reason": exam.error_reason,
        }

    def _essay_item(self, essay: Essay) -> dict[str, Any]:
        return {
            "id": essay.id,
            "theme": essay.theme,
            "date": essay.date.isoformat() if essay.date else None,
            "total_score": essay.total_score,
            "c1": essay.c1,
            "c2": essay.c2,
            "c3": essay.c3,
            "c4": essay.c4,
            "c5": essay.c5,
            "observation": "registro de evolução, não correção oficial",
        }


def build_student_context(user_id: int, db: Session) -> dict[str, Any]:
    return AIContextService(db).build_student_context(user_id)
