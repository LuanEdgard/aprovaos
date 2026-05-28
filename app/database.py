from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    apply_sqlite_schema_updates()


def apply_sqlite_schema_updates() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    updates = {
        "users": {
            "is_admin": "BOOLEAN DEFAULT 0 NOT NULL",
        },
        "user_profiles": {
            "serie": "VARCHAR(120)",
            "rotina_resumo": "TEXT",
            "carga_horaria_disponivel": "VARCHAR(120)",
            "vestibulares_alvo": "TEXT",
            "principais_dificuldades": "TEXT",
            "metas": "TEXT",
            "observacoes": "TEXT",
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        },
        "routine_blocks": {
            "type": "VARCHAR(60)",
            "day_of_week": "INTEGER",
            "description": "TEXT",
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        },
        "subject_topics": {
            "status": "VARCHAR(40)",
            "difficulty": "VARCHAR(20)",
        },
        "materials": {
            "type": "VARCHAR(60)",
            "source": "VARCHAR(80)",
            "subject_id": "INTEGER",
            "topic": "VARCHAR(140)",
            "subtopic": "VARCHAR(140)",
            "ai_summary": "TEXT",
            "ai_detected_subject": "VARCHAR(120)",
            "ai_detected_topic": "VARCHAR(140)",
            "ai_detected_subtopic": "VARCHAR(140)",
            "updated_at": "DATETIME",
        },
        "study_tasks": {
            "description": "TEXT",
            "task_category": "VARCHAR(80)",
            "source": "VARCHAR(80)",
            "origin": "VARCHAR(80)",
            "subject_id": "INTEGER",
            "front_id": "INTEGER",
            "topic_id": "INTEGER",
            "subtopic": "VARCHAR(140)",
            "due_date": "DATE",
            "ai_description": "TEXT",
            "completed_at": "DATETIME",
            "updated_at": "DATETIME",
        },
        "flashcard_decks": {
            "name": "VARCHAR(160)",
            "subject_id": "INTEGER",
            "front_id": "INTEGER",
            "topic": "VARCHAR(140)",
            "source": "VARCHAR(80)",
            "description": "TEXT",
        },
        "flashcards": {
            "subject_id": "INTEGER",
            "front_id": "INTEGER",
            "topic_id": "INTEGER",
            "tag": "VARCHAR(255)",
            "last_reviewed_at": "DATETIME",
            "interval_days": "INTEGER",
            "ease_factor": "FLOAT",
            "repetitions": "INTEGER",
            "updated_at": "DATETIME",
        },
        "exam_results": {
            "score_by_area": "TEXT",
            "correct_by_subject": "TEXT",
            "duration_minutes": "INTEGER",
            "updated_at": "DATETIME",
        },
        "essays": {
            "teacher_comments": "TEXT",
            "repertoire_used": "TEXT",
            "improvement_points": "TEXT",
            "updated_at": "DATETIME",
        },
        "calendar_events": {
            "description": "TEXT",
            "source_type": "VARCHAR(80)",
            "source_id": "VARCHAR(120)",
            "external_id": "VARCHAR(120)",
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        },
        "chat_messages": {
            "metadata_json": "TEXT",
        },
        "ai_provider_configs": {
            "use_for_recovery": "BOOLEAN DEFAULT 1 NOT NULL",
            "use_for_general": "BOOLEAN DEFAULT 1 NOT NULL",
            "last_successful_tested_at": "DATETIME",
        },
    }

    with engine.begin() as connection:
        for table, columns in updates.items():
            existing = {
                row[1]
                for row in connection.execute(text(f"PRAGMA table_info({table})")).fetchall()
            }
            if not existing:
                continue
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}"))

        _backfill_compatibility_columns(connection)


def _backfill_compatibility_columns(connection) -> None:
    statements = [
        "UPDATE user_profiles SET serie = COALESCE(serie, school_year), rotina_resumo = COALESCE(rotina_resumo, study_profile_summary), vestibulares_alvo = COALESCE(vestibulares_alvo, target_exams), principais_dificuldades = COALESCE(principais_dificuldades, main_difficulty), created_at = COALESCE(created_at, CURRENT_TIMESTAMP), updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)",
        "UPDATE routine_blocks SET type = COALESCE(type, block_type), day_of_week = COALESCE(day_of_week, weekday), description = COALESCE(description, notes)",
        "UPDATE subject_topics SET status = COALESCE(status, 'nao_iniciado'), difficulty = COALESCE(difficulty, 'media')",
        "UPDATE materials SET type = COALESCE(type, material_type), source = COALESCE(source, source_type), ai_summary = COALESCE(ai_summary, summary)",
        "UPDATE study_tasks SET source = COALESCE(source, source_type), origin = COALESCE(origin, source, source_type), due_date = COALESCE(due_date, deadline), task_category = COALESCE(task_category, 'other'), completed_at = COALESCE(completed_at, CASE WHEN status IN ('completed', 'concluída') THEN updated_at END)",
        "UPDATE flashcard_decks SET name = COALESCE(name, title), source = COALESCE(source, source_type)",
        "UPDATE flashcards SET last_reviewed_at = COALESCE(last_reviewed_at, last_review_at), interval_days = COALESCE(interval_days, 1), ease_factor = COALESCE(ease_factor, 2.5), repetitions = COALESCE(repetitions, review_count), updated_at = COALESCE(updated_at, created_at)",
        "UPDATE essays SET teacher_comments = COALESCE(teacher_comments, corrector_feedback), repertoire_used = COALESCE(repertoire_used, repertoires_used), improvement_points = COALESCE(improvement_points, intervention_notes)",
        "UPDATE calendar_events SET description = COALESCE(description, notes), source_type = COALESCE(source_type, 'manual'), source_id = COALESCE(source_id, CAST(related_task_id AS TEXT)), external_id = COALESCE(external_id, source_id)",
    ]
    for statement in statements:
        connection.execute(text(statement))

    users = connection.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0
    admins = connection.execute(text("SELECT COUNT(*) FROM users WHERE is_admin = 1")).scalar() or 0
    if users and not admins:
        connection.execute(text("UPDATE users SET is_admin = 1 WHERE id = (SELECT MIN(id) FROM users)"))
