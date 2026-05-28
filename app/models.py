from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import relationship

from app.database import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    age = Column(Integer, nullable=True)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)

    profile = relationship("UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    routine_blocks = relationship("RoutineBlock", back_populates="user", cascade="all, delete-orphan")
    subjects = relationship("Subject", back_populates="user", cascade="all, delete-orphan")
    materials = relationship("Material", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("StudyTask", back_populates="user", cascade="all, delete-orphan")
    decks = relationship("FlashcardDeck", back_populates="user", cascade="all, delete-orphan")
    flashcards = relationship("Flashcard", back_populates="user", cascade="all, delete-orphan")
    flashcard_reviews = relationship("FlashcardReview", back_populates="user", cascade="all, delete-orphan")
    exams = relationship("ExamResult", back_populates="user", cascade="all, delete-orphan")
    essays = relationship("Essay", back_populates="user", cascade="all, delete-orphan")
    calendar_events = relationship("CalendarEvent", back_populates="user", cascade="all, delete-orphan")
    plans = relationship("AIPlan", back_populates="user", cascade="all, delete-orphan")
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    ai_provider_configs = relationship("AIProviderConfig", back_populates="created_by_user")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    school_year = Column(String(120), nullable=True)
    serie = Column(String(120), nullable=True)
    routine_type = Column(String(255), nullable=True)
    rotina_resumo = Column(Text, nullable=True)
    carga_horaria_disponivel = Column(String(120), nullable=True)
    target_course = Column(String(160), nullable=True)
    target_universities = Column(Text, nullable=True)
    target_exams = Column(Text, nullable=True)
    vestibulares_alvo = Column(Text, nullable=True)
    main_difficulty = Column(String(160), nullable=True)
    principais_dificuldades = Column(Text, nullable=True)
    metas = Column(Text, nullable=True)
    observacoes = Column(Text, nullable=True)
    weekly_priority = Column(String(80), default="Equilíbrio", nullable=False)
    overload_risk = Column(String(80), default="moderado", nullable=False)
    study_profile_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    user = relationship("User", back_populates="profile")


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    theme = Column(String(20), default="escuro", nullable=False)
    notify_reviews = Column(String(10), default="sim", nullable=False)
    notify_weekly_summary = Column(String(10), default="não", nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    user = relationship("User", back_populates="settings")


class RoutineBlock(Base):
    __tablename__ = "routine_blocks"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(160), nullable=False)
    block_type = Column(String(60), nullable=False)
    type = Column(String(60), nullable=True)
    weekday = Column(Integer, nullable=False)
    day_of_week = Column(Integer, nullable=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    recurrence = Column(String(60), default="semanal", nullable=False)
    notes = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    user = relationship("User", back_populates="routine_blocks")


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    area = Column(String(80), nullable=False, default="Outros")
    source_type = Column(String(80), nullable=False, default="personal")
    color = Column(String(24), nullable=False, default="#3b82f6")
    is_active = Column(Boolean, default=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    user = relationship("User", back_populates="subjects")
    fronts = relationship("SubjectFront", back_populates="subject", cascade="all, delete-orphan")
    topics = relationship("SubjectTopic", back_populates="subject", cascade="all, delete-orphan")
    materials = relationship("Material", back_populates="subject_ref")
    tasks = relationship("StudyTask", back_populates="subject_ref")
    decks = relationship("FlashcardDeck", back_populates="subject_ref")
    flashcards = relationship("Flashcard", back_populates="subject_ref")


class SubjectFront(Base):
    __tablename__ = "subject_fronts"

    id = Column(Integer, primary_key=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    name = Column(String(140), nullable=False)
    description = Column(Text, nullable=True)
    order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    subject = relationship("Subject", back_populates="fronts")
    topics = relationship("SubjectTopic", back_populates="front")


class SubjectTopic(Base):
    __tablename__ = "subject_topics"

    id = Column(Integer, primary_key=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    front_id = Column(Integer, ForeignKey("subject_fronts.id"), nullable=True, index=True)
    name = Column(String(140), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(40), default="nao_iniciado", nullable=False)
    difficulty = Column(String(20), default="media", nullable=False)
    order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    subject = relationship("Subject", back_populates="topics")
    front = relationship("SubjectFront", back_populates="topics")


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(180), nullable=False)
    material_type = Column(String(60), nullable=False)
    type = Column(String(60), nullable=True)
    source_type = Column(String(80), nullable=False)
    source = Column(String(80), nullable=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True, index=True)
    subject = Column(String(100), nullable=True)
    topic = Column(String(140), nullable=True)
    subtopic = Column(String(140), nullable=True)
    tags = Column(String(255), nullable=True)
    file_path = Column(String(500), nullable=True)
    extracted_text = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    ai_summary = Column(Text, nullable=True)
    ai_detected_subject = Column(String(120), nullable=True)
    ai_detected_topic = Column(String(140), nullable=True)
    ai_detected_subtopic = Column(String(140), nullable=True)
    status = Column(String(80), default="enviado", nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    user = relationship("User", back_populates="materials")
    subject_ref = relationship("Subject", back_populates="materials")
    tasks = relationship("StudyTask", back_populates="material")
    flashcards = relationship("Flashcard", back_populates="material")


class StudyTask(Base):
    __tablename__ = "study_tasks"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=True)
    title = Column(String(180), nullable=False)
    description = Column(Text, nullable=True)
    task_category = Column(String(80), default="other", nullable=False)
    source = Column(String(80), nullable=True)
    origin = Column(String(80), nullable=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True, index=True)
    front_id = Column(Integer, ForeignKey("subject_fronts.id"), nullable=True, index=True)
    topic_id = Column(Integer, ForeignKey("subject_topics.id"), nullable=True, index=True)
    subject = Column(String(100), nullable=True)
    subtopic = Column(String(140), nullable=True)
    source_type = Column(String(80), nullable=False)
    priority = Column(String(60), default="média", nullable=False)
    status = Column(String(60), default="pendente", nullable=False)
    deadline = Column(Date, nullable=True)
    due_date = Column(Date, nullable=True)
    estimated_minutes = Column(Integer, default=50, nullable=False)
    ai_description = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    user = relationship("User", back_populates="tasks")
    material = relationship("Material", back_populates="tasks")
    subject_ref = relationship("Subject", back_populates="tasks")
    front_ref = relationship("SubjectFront")
    topic_ref = relationship("SubjectTopic")
    calendar_events = relationship("CalendarEvent", back_populates="related_task")


class FlashcardDeck(Base):
    __tablename__ = "flashcard_decks"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(160), nullable=False)
    name = Column(String(160), nullable=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True, index=True)
    front_id = Column(Integer, ForeignKey("subject_fronts.id"), nullable=True, index=True)
    subject = Column(String(100), nullable=True)
    topic = Column(String(140), nullable=True)
    description = Column(Text, nullable=True)
    source = Column(String(80), nullable=True)
    source_type = Column(String(80), default="pessoal", nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)

    user = relationship("User", back_populates="decks")
    subject_ref = relationship("Subject", back_populates="decks")
    front_ref = relationship("SubjectFront")
    flashcards = relationship("Flashcard", back_populates="deck", cascade="all, delete-orphan")


class Flashcard(Base):
    __tablename__ = "flashcards"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    deck_id = Column(Integer, ForeignKey("flashcard_decks.id"), nullable=False)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True, index=True)
    front_id = Column(Integer, ForeignKey("subject_fronts.id"), nullable=True, index=True)
    topic_id = Column(Integer, ForeignKey("subject_topics.id"), nullable=True, index=True)
    subject = Column(String(100), nullable=True)
    topic = Column(String(140), nullable=True)
    front = Column(Text, nullable=False)
    back = Column(Text, nullable=False)
    tag = Column(String(255), nullable=True)
    difficulty = Column(String(60), default="novo", nullable=False)
    next_review_at = Column(DateTime(timezone=True), nullable=True)
    last_review_at = Column(DateTime(timezone=True), nullable=True)
    last_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_count = Column(Integer, default=0, nullable=False)
    interval_days = Column(Integer, default=1, nullable=False)
    ease_factor = Column(Float, default=2.5, nullable=False)
    repetitions = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    user = relationship("User", back_populates="flashcards")
    deck = relationship("FlashcardDeck", back_populates="flashcards")
    material = relationship("Material", back_populates="flashcards")
    subject_ref = relationship("Subject", back_populates="flashcards")
    front_ref = relationship("SubjectFront")
    topic_ref = relationship("SubjectTopic")
    reviews = relationship("FlashcardReview", back_populates="flashcard", cascade="all, delete-orphan")


class FlashcardReview(Base):
    __tablename__ = "flashcard_reviews"

    id = Column(Integer, primary_key=True)
    flashcard_id = Column(Integer, ForeignKey("flashcards.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    response = Column(String(20), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    next_review_at = Column(DateTime(timezone=True), nullable=True)

    flashcard = relationship("Flashcard", back_populates="reviews")
    user = relationship("User", back_populates="flashcard_reviews")


class ExamResult(Base):
    __tablename__ = "exam_results"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    exam_type = Column(String(80), nullable=False)
    date = Column(Date, nullable=False)
    total_score = Column(Float, nullable=True)
    score_languages = Column(Float, nullable=True)
    score_human_sciences = Column(Float, nullable=True)
    score_natural_sciences = Column(Float, nullable=True)
    score_math = Column(Float, nullable=True)
    essay_score = Column(Float, nullable=True)
    score_by_area = Column(Text, nullable=True)
    correct_by_subject = Column(Text, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    main_mistakes = Column(Text, nullable=True)
    error_reason = Column(String(80), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    user = relationship("User", back_populates="exams")


class Essay(Base):
    __tablename__ = "essays"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    theme = Column(String(220), nullable=False)
    date = Column(Date, nullable=False)
    total_score = Column(Float, nullable=True)
    c1 = Column(Float, nullable=True)
    c2 = Column(Float, nullable=True)
    c3 = Column(Float, nullable=True)
    c4 = Column(Float, nullable=True)
    c5 = Column(Float, nullable=True)
    corrector_feedback = Column(Text, nullable=True)
    teacher_comments = Column(Text, nullable=True)
    recurring_errors = Column(Text, nullable=True)
    repertoires_used = Column(Text, nullable=True)
    repertoire_used = Column(Text, nullable=True)
    intervention_notes = Column(Text, nullable=True)
    improvement_points = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    user = relationship("User", back_populates="essays")


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(180), nullable=False)
    event_type = Column(String(80), nullable=False)
    start_datetime = Column(DateTime(timezone=True), nullable=False)
    end_datetime = Column(DateTime(timezone=True), nullable=True)
    related_task_id = Column(Integer, ForeignKey("study_tasks.id"), nullable=True)
    notes = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(60), default="pendente", nullable=False)
    source_type = Column(String(80), nullable=True)
    source_id = Column(String(120), nullable=True)
    external_id = Column(String(120), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    user = relationship("User", back_populates="calendar_events")
    related_task = relationship("StudyTask", back_populates="calendar_events")


class AIPlan(Base):
    __tablename__ = "ai_plans"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    week_start = Column(Date, nullable=False)
    weekly_priority = Column(String(80), nullable=False)
    plan_text = Column(Text, nullable=False)
    rationale = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)

    user = relationship("User", back_populates="plans")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(180), nullable=False, default="Nova conversa")
    mode = Column(String(80), nullable=False, default="organizer")
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)

    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String(40), nullable=False)
    content = Column(Text, nullable=False)
    cited_material_ids = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)

    session = relationship("ChatSession", back_populates="messages")


class AIProviderConfig(Base):
    __tablename__ = "ai_provider_configs"

    id = Column(Integer, primary_key=True)
    provider_name = Column(String(40), nullable=False, unique=True, index=True)
    encrypted_api_key = Column(Text, nullable=True)
    key_preview = Column(String(80), nullable=True)
    default_model = Column(String(120), nullable=True)
    enabled = Column(Boolean, default=False, nullable=False)
    priority = Column(Integer, default=100, nullable=False)
    use_for_tutor = Column(Boolean, default=True, nullable=False)
    use_for_materials = Column(Boolean, default=True, nullable=False)
    use_for_flashcards = Column(Boolean, default=True, nullable=False)
    use_for_planning = Column(Boolean, default=True, nullable=False)
    use_for_reports = Column(Boolean, default=True, nullable=False)
    use_for_recovery = Column(Boolean, default=True, nullable=False)
    use_for_general = Column(Boolean, default=True, nullable=False)
    last_test_status = Column(String(60), default="not_configured", nullable=False)
    last_test_error = Column(Text, nullable=True)
    last_tested_at = Column(DateTime(timezone=True), nullable=True)
    last_successful_tested_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_by_user = relationship("User", back_populates="ai_provider_configs")


class AIRoutingConfig(Base):
    __tablename__ = "ai_routing_configs"

    id = Column(Integer, primary_key=True)
    module_name = Column(String(80), nullable=False, unique=True, index=True)
    provider_name = Column(String(40), nullable=False)
    model = Column(String(120), nullable=True)
    fallback_order = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    provider_name = Column(String(40), nullable=False)
    model = Column(String(120), nullable=True)
    module_name = Column(String(80), nullable=False)
    request_type = Column(String(120), nullable=False)
    success = Column(Boolean, default=False, nullable=False)
    error_message = Column(Text, nullable=True)
    estimated_input_tokens = Column(Integer, nullable=True)
    estimated_output_tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, nullable=False)
