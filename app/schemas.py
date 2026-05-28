from datetime import date, datetime, time
import unicodedata

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.services.normalization import (
    normalize_material_type,
    normalize_routine_type,
    normalize_source,
    normalize_status,
    normalize_task_category,
)


WEEKLY_PRIORITIES = {"Escola", "Vestibular", "Equilíbrio", "Recuperação"}
ROUTINE_TYPES = {"school", "course", "transport", "work", "sleep", "rest", "personal", "study_window", "other", "escola", "cursinho", "estudo", "transporte", "descanso", "trabalho", "pessoal", "sono"}
TASK_CATEGORIES = {"watch_lesson", "review_lesson", "do_exercises", "essay", "mock_exam", "school_work", "reading", "flashcard_review", "material_review", "correction_review", "other"}
TASK_SOURCES = {"school", "course", "vestibular", "personal", "technical_course", "other", "escola", "cursinho", "redação", "simulado", "revisão", "materiais enviados", "pessoal"}
TASK_PRIORITIES = {"baixa", "média", "alta", "urgente"}
TASK_STATUSES = {"pending", "completed", "late", "rescheduled", "pendente", "concluída", "atrasada", "reagendada"}
MATERIAL_TYPES = {"pdf", "text", "docx", "image", "slides", "exercise_list", "essay_correction", "schedule", "notes", "other", "texto", "imagem", "edital", "correção", "lista", "aula"}
MATERIAL_STATUSES = {"enviado", "processado", "precisa revisar", "arquivado"}
EXAM_TYPES = {"ENEM", "FUVEST", "UFBA", "UnB", "UFPE", "escola", "personalizado"}
ERROR_REASONS = {"conteúdo", "interpretação", "atenção", "tempo", "chute", "falta de revisão"}
EVENT_TYPES = {"escola", "cursinho", "simulado", "redação", "revisão", "material", "descanso", "prova"}
EVENT_STATUSES = {"pendente", "concluído", "perdido"}
TUTOR_MODES = {"Organizador", "Analista", "Tutor com fontes", "Criador de flashcards", "Recuperação", "Priorizador"}

WEEKLY_PRIORITY_MAP = {
    "escola": "Escola",
    "vestibular": "Vestibular",
    "equilibrio": "Equilíbrio",
    "equil?brio": "Equilíbrio",
    "recuperacao": "Recuperação",
    "recupera??o": "Recuperação",
}
TASK_SOURCE_MAP = {
    "school": "school",
    "escola": "school",
    "course": "course",
    "cursinho": "course",
    "vestibular": "vestibular",
    "redacao": "vestibular",
    "simulado": "vestibular",
    "revisao": "personal",
    "materiais enviados": "personal",
    "personal": "personal",
    "pessoal": "personal",
    "technical_course": "technical_course",
    "curso tecnico": "technical_course",
    "other": "other",
    "outro": "other",
}
TASK_STATUS_MAP = {
    "pending": "pending",
    "pendente": "pending",
    "completed": "completed",
    "concluida": "completed",
    "late": "late",
    "atrasada": "late",
    "rescheduled": "rescheduled",
    "reagendada": "rescheduled",
}
TASK_PRIORITY_MAP = {
    "baixa": "baixa",
    "media": "média",
    "alta": "alta",
    "urgente": "urgente",
}
MATERIAL_TYPE_MAP = {
    "pdf": "pdf",
    "text": "text",
    "texto": "text",
    "docx": "docx",
    "image": "image",
    "imagem": "image",
    "slides": "slides",
    "edital": "other",
    "correcao": "essay_correction",
    "lista": "exercise_list",
    "aula": "notes",
    "notes": "notes",
    "other": "other",
}
ERROR_REASON_MAP = {
    "conteudo": "conteúdo",
    "interpretacao": "interpretação",
    "atencao": "atenção",
    "tempo": "tempo",
    "chute": "chute",
    "falta de revisao": "falta de revisão",
}
EVENT_TYPE_MAP = {
    "school": "school",
    "escola": "school",
    "course": "course",
    "cursinho": "course",
    "simulation": "simulation",
    "simulado": "simulation",
    "essay": "essay",
    "redacao": "essay",
    "flashcard_review": "flashcard_review",
    "revisao": "flashcard_review",
    "material": "material",
    "rest": "rest",
    "descanso": "rest",
    "prova": "simulation",
}
EVENT_STATUS_MAP = {
    "pending": "pending",
    "pendente": "pending",
    "completed": "completed",
    "concluido": "completed",
    "missed": "missed",
    "perdido": "missed",
}
TUTOR_MODE_MAP = {
    "organizer": "Organizer",
    "organizador": "Organizador",
    "analyst": "Analyst",
    "analista": "Analista",
    "tutor with sources": "Tutor with sources",
    "tutor com fontes": "Tutor com fontes",
    "flashcard creator": "Flashcard creator",
    "criador de flashcards": "Criador de flashcards",
    "recovery": "Recovery",
    "recuperacao": "Recuperação",
    "prioritizer": "Prioritizer",
    "priorizador": "Prioritizer",
}


def _repair_text(value: str) -> str:
    value = value.strip()
    if "Ã" in value or "Â" in value:
        try:
            value = value.encode("latin1").decode("utf-8")
        except UnicodeError:
            pass
    return value


def _key(value: str) -> str:
    repaired = _repair_text(value).lower()
    return "".join(
        char for char in unicodedata.normalize("NFKD", repaired)
        if not unicodedata.combining(char)
    )


def _coerce(value: str, mapping: dict[str, str], message: str) -> str:
    key = _key(value)
    if key not in mapping:
        raise ValueError(message)
    return mapping[key]


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class OnboardingRequest(BaseModel):
    name: str | None = None
    age: int | None = Field(default=None, ge=10, le=100)
    school_year: str | None = None
    routine_type: str | None = None
    target_exams: str | None = None
    target_course: str | None = None
    target_universities: str | None = None
    uses_cursinho: str | None = None
    cursinho_name: str | None = None
    school_schedule: str | None = None
    cursinho_schedule: str | None = None
    transport_time: str | None = None
    sleep_schedule: str | None = None
    free_hours_per_day: str | None = None
    strong_subjects: str | None = None
    weak_subjects: str | None = None
    latest_scores: str | None = None
    essay_scores: str | None = None
    main_difficulty: str | None = None
    weekly_priority: str = "Equilíbrio"

    @field_validator("weekly_priority")
    @classmethod
    def validate_weekly_priority(cls, value: str) -> str:
        return _coerce(value, WEEKLY_PRIORITY_MAP, "Prioridade semanal inválida.")


class RoutineBlockCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    block_type: str
    weekday: int | None = Field(default=None, ge=0, le=6)
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    start_time: time
    end_time: time
    recurrence: str = "weekly"
    notes: str | None = None
    description: str | None = None

    @field_validator("block_type")
    @classmethod
    def validate_block_type(cls, value: str) -> str:
        value = normalize_routine_type(value)
        if value not in {"school", "course", "transport", "work", "sleep", "rest", "personal", "study_window", "other"}:
            raise ValueError("Tipo de bloco inválido.")
        return value

    @model_validator(mode="after")
    def validate_time_range(self) -> "RoutineBlockCreate":
        if self.weekday is None and self.day_of_week is None:
            raise ValueError("Informe o dia da semana.")
        if self.weekday is None:
            self.weekday = self.day_of_week
        if self.day_of_week is None:
            self.day_of_week = self.weekday
        self.description = self.description or self.notes
        self.notes = self.notes or self.description
        if self.end_time <= self.start_time:
            raise ValueError("O horário final precisa ser posterior ao horário inicial.")
        return self


class RoutineBlockUpdate(RoutineBlockCreate):
    pass


class RoutineProfileUpdate(BaseModel):
    vestibulares_alvo: str | None = None
    serie: str | None = None
    rotina_resumo: str | None = None
    carga_horaria_disponivel: str | None = None
    principais_dificuldades: str | None = None
    metas: str | None = None
    observacoes: str | None = None


class RoutinePlannerRequest(BaseModel):
    message: str = Field(min_length=3, max_length=500)


class RoutinePlannerConfirmRequest(BaseModel):
    suggestions: list[dict[str, object]] = Field(default_factory=list)


class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    description: str | None = None
    task_category: str = "other"
    source: str | None = None
    origin: str | None = None
    subject_id: int | None = None
    front_id: int | None = None
    topic_id: int | None = None
    subject: str | None = None
    subtopic: str | None = None
    source_type: str = "pessoal"
    priority: str = "média"
    status: str = "pending"
    deadline: date | None = None
    due_date: date | None = None
    estimated_minutes: int = Field(default=50, ge=5, le=600)
    material_id: int | None = None
    ai_description: str | None = None

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, value: str) -> str:
        return normalize_source(value)

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str | None) -> str | None:
        return normalize_source(value) if value else value

    @field_validator("task_category")
    @classmethod
    def validate_task_category(cls, value: str) -> str:
        category = normalize_task_category(value)
        if category not in TASK_CATEGORIES:
            raise ValueError("Categoria da pendência inválida.")
        return category

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        return _coerce(value, TASK_PRIORITY_MAP, "Prioridade inválida.")

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        return normalize_status(value)

    @model_validator(mode="after")
    def sync_compat_fields(self) -> "TaskCreate":
        self.source = self.source or self.source_type
        self.source_type = self.source_type or self.source
        self.origin = self.origin or self.source or self.source_type
        self.due_date = self.due_date or self.deadline
        self.deadline = self.deadline or self.due_date
        self.ai_description = self.ai_description or self.description
        return self


class TaskUpdate(TaskCreate):
    pass


class RescheduleRequest(BaseModel):
    mode: str = "Recuperação"

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        return _coerce(value, WEEKLY_PRIORITY_MAP, "Modo de reorganização inválido.")


class MaterialTextCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    material_type: str = "text"
    source_type: str = "personal"
    type: str | None = None
    source: str | None = None
    subject_id: int | None = None
    subject: str | None = None
    topic: str | None = None
    subtopic: str | None = None
    tags: str | None = None
    text: str = Field(min_length=1)

    @field_validator("material_type")
    @classmethod
    def validate_material_type(cls, value: str) -> str:
        return normalize_material_type(value)

    @field_validator("source_type")
    @classmethod
    def validate_material_source(cls, value: str) -> str:
        return normalize_source(value)

    @model_validator(mode="after")
    def sync_material_fields(self) -> "MaterialTextCreate":
        self.type = normalize_material_type(self.type or self.material_type)
        self.material_type = self.type
        self.source = normalize_source(self.source or self.source_type)
        self.source_type = self.source
        return self


class FlashcardCreate(BaseModel):
    deck_id: int | None = None
    deck_title: str | None = None
    subject_id: int | None = None
    front_id: int | None = None
    topic_id: int | None = None
    subject: str | None = None
    topic: str | None = None
    front: str = Field(min_length=2)
    back: str = Field(min_length=2)
    tag: str | None = None
    material_id: int | None = None


class FlashcardReviewRequest(BaseModel):
    answer_quality: str

    @field_validator("answer_quality")
    @classmethod
    def validate_quality(cls, value: str) -> str:
        allowed = {
            "errei": "Errei",
            "dificil": "Difícil",
            "medio": "Médio",
            "facil": "Fácil",
        }
        key = _key(value)
        if key not in allowed:
            raise ValueError("Resposta de revisão inválida.")
        return allowed[key]


class ExamCreate(BaseModel):
    exam_type: str
    date: date
    total_score: float | None = Field(default=None, ge=0, le=1000)
    score_languages: float | None = Field(default=None, ge=0, le=1000)
    score_human_sciences: float | None = Field(default=None, ge=0, le=1000)
    score_natural_sciences: float | None = Field(default=None, ge=0, le=1000)
    score_math: float | None = Field(default=None, ge=0, le=1000)
    essay_score: float | None = Field(default=None, ge=0, le=1000)
    score_by_area: str | None = None
    correct_by_subject: str | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=720)
    notes: str | None = None
    main_mistakes: str | None = None
    error_reason: str | None = None

    @field_validator("exam_type")
    @classmethod
    def validate_exam_type(cls, value: str) -> str:
        if value not in EXAM_TYPES:
            raise ValueError("Tipo de simulado inválido.")
        return value

    @field_validator("error_reason")
    @classmethod
    def validate_error_reason(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        return _coerce(value, ERROR_REASON_MAP, "Motivo de erro inválido.")


class EssayCreate(BaseModel):
    theme: str = Field(min_length=2, max_length=220)
    date: date
    total_score: float | None = Field(default=None, ge=0, le=1000)
    c1: float | None = Field(default=None, ge=0, le=200)
    c2: float | None = Field(default=None, ge=0, le=200)
    c3: float | None = Field(default=None, ge=0, le=200)
    c4: float | None = Field(default=None, ge=0, le=200)
    c5: float | None = Field(default=None, ge=0, le=200)
    corrector_feedback: str | None = None
    teacher_comments: str | None = None
    recurring_errors: str | None = None
    repertoires_used: str | None = None
    repertoire_used: str | None = None
    intervention_notes: str | None = None
    improvement_points: str | None = None

    @model_validator(mode="after")
    def sync_essay_fields(self) -> "EssayCreate":
        self.teacher_comments = self.teacher_comments or self.corrector_feedback
        self.corrector_feedback = self.corrector_feedback or self.teacher_comments
        self.repertoire_used = self.repertoire_used or self.repertoires_used
        self.repertoires_used = self.repertoires_used or self.repertoire_used
        self.improvement_points = self.improvement_points or self.intervention_notes
        self.intervention_notes = self.intervention_notes or self.improvement_points
        return self


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    event_type: str
    start_datetime: datetime
    end_datetime: datetime | None = None
    related_task_id: int | None = None
    notes: str | None = None
    description: str | None = None
    status: str = "pendente"

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        return _coerce(value, EVENT_TYPE_MAP, "Tipo de evento inválido.")

    @field_validator("status")
    @classmethod
    def validate_event_status(cls, value: str) -> str:
        return _coerce(value, EVENT_STATUS_MAP, "Situação do evento inválida.")

    @model_validator(mode="after")
    def validate_event_range(self) -> "CalendarEventCreate":
        if self.end_datetime and self.end_datetime <= self.start_datetime:
            raise ValueError("O fim do evento precisa ser posterior ao início.")
        self.description = self.description or self.notes
        self.notes = self.notes or self.description
        return self


class SubjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    area: str = Field(default="Outros", max_length=80)
    source_type: str = "personal"
    color: str = Field(default="#3b82f6", max_length=24)
    description: str | None = None

    @field_validator("source_type")
    @classmethod
    def validate_subject_source(cls, value: str) -> str:
        return normalize_source(value)


class SubjectFrontCreate(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    description: str | None = None
    order: int = 0


class SubjectTopicCreate(BaseModel):
    name: str = Field(min_length=2, max_length=140)
    front_id: int | None = None
    description: str | None = None
    status: str = "nao_iniciado"
    difficulty: str = "media"
    order: int = 0

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        clean = _key(value)
        allowed = {"nao_iniciado", "em_andamento", "concluido", "revisar"}
        if clean not in allowed:
            raise ValueError("Status do assunto inválido.")
        return clean

    @field_validator("difficulty")
    @classmethod
    def validate_difficulty(cls, value: str) -> str:
        clean = _key(value)
        allowed = {"baixa", "media", "alta"}
        if clean not in allowed:
            raise ValueError("Dificuldade do assunto inválida.")
        return clean


class TutorChatRequest(BaseModel):
    session_id: int | None = None
    mode: str = "organizer"
    message: str = Field(min_length=1, max_length=4000)
    material_id: int | None = None


AI_CHAT_MODES = {
    "organizador",
    "analista",
    "tutor_fontes",
    "flashcards",
    "recuperacao",
    "priorizador",
    "organizer",
    "analyst",
    "tutor with sources",
    "flashcard creator",
    "recovery",
    "prioritizer",
}


class AIChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    mode: str = "organizador"
    conversation_id: int | None = None
    material_id: int | None = None

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        mode = value.strip().lower()
        if mode not in AI_CHAT_MODES:
            raise ValueError("Modo de IA inválido.")
        return mode


class AIConversationCreateRequest(BaseModel):
    mode: str = "organizador"
    title: str | None = Field(default=None, max_length=180)

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        mode = value.strip().lower()
        if mode not in AI_CHAT_MODES:
            raise ValueError("Modo de IA inválido.")
        return mode


class AIActionApplyRequest(BaseModel):
    action: str = Field(min_length=2, max_length=80)
    payload: dict[str, object] = Field(default_factory=dict)


class AIMaterialAskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=3000)


class TutorMessageRequest(BaseModel):
    mode: str = "Organizador"
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("mode")
    @classmethod
    def validate_tutor_mode(cls, value: str) -> str:
        return _coerce(value, TUTOR_MODE_MAP, "Modo do Tutor IA inválido.")


class WeeklyPriorityRequest(BaseModel):
    weekly_priority: str

    @field_validator("weekly_priority")
    @classmethod
    def validate_priority_value(cls, value: str) -> str:
        return _coerce(value, WEEKLY_PRIORITY_MAP, "Prioridade semanal inválida.")


class SettingsUpdate(BaseModel):
    theme: str = "escuro"
    notify_reviews: bool = True
    notify_weekly_summary: bool = False

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"claro", "escuro"}:
            raise ValueError("Tema inválido.")
        return value


AI_PROVIDERS = {"openai", "gemini", "deepseek"}
AI_MODULES = {"tutor", "materials", "flashcards", "planning", "reports", "recovery", "general"}


class AIKeySaveRequest(BaseModel):
    api_key: str = Field(min_length=8, max_length=4096)
    default_model: str | None = Field(default=None, max_length=120)
    enabled: bool = True
    use_for_tutor: bool = True
    use_for_materials: bool = True
    use_for_flashcards: bool = True
    use_for_planning: bool = True
    use_for_reports: bool = True
    use_for_recovery: bool = True
    use_for_general: bool = True


class AIProviderUpdate(BaseModel):
    default_model: str | None = Field(default=None, max_length=120)
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=999)
    use_for_tutor: bool | None = None
    use_for_materials: bool | None = None
    use_for_flashcards: bool | None = None
    use_for_planning: bool | None = None
    use_for_reports: bool | None = None
    use_for_recovery: bool | None = None
    use_for_general: bool | None = None


class AIRoutingItem(BaseModel):
    module_name: str
    provider_name: str
    model: str | None = Field(default=None, max_length=120)
    fallback_order: list[str] = Field(default_factory=list)

    @field_validator("module_name")
    @classmethod
    def validate_module_name(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in AI_MODULES:
            raise ValueError("Módulo de IA inválido.")
        return value

    @field_validator("provider_name")
    @classmethod
    def validate_provider_name(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in AI_PROVIDERS:
            raise ValueError("Provedor de IA inválido.")
        return value

    @field_validator("fallback_order")
    @classmethod
    def validate_fallback_order(cls, value: list[str]) -> list[str]:
        clean = []
        for item in value:
            provider = str(item).strip().lower()
            if provider in AI_PROVIDERS and provider not in clean:
                clean.append(provider)
        return clean


class AIRoutingUpdate(BaseModel):
    routes: list[AIRoutingItem]
