import re
import unicodedata


SOURCE_LABELS = {
    "school": "Escola",
    "course": "Cursinho",
    "vestibular": "Vestibular",
    "personal": "Pessoal",
    "technical_course": "Curso técnico",
    "other": "Outro",
}

SOURCE_ALIASES = {
    "escola": "school",
    "school": "school",
    "cursinho": "course",
    "curso": "course",
    "course": "course",
    "vestibular": "vestibular",
    "enem": "vestibular",
    "pessoal": "personal",
    "personal": "personal",
    "curso tecnico": "technical_course",
    "tecnico": "technical_course",
    "technical_course": "technical_course",
    "outro": "other",
    "other": "other",
    "redacao": "vestibular",
    "simulado": "vestibular",
    "revisao": "personal",
    "materiais enviados": "personal",
}

TASK_CATEGORY_LABELS = {
    "watch_lesson": "Assistir aula",
    "review_lesson": "Revisar aula",
    "do_exercises": "Fazer exercícios",
    "essay": "Redação",
    "mock_exam": "Simulado",
    "school_work": "Trabalho escolar",
    "reading": "Leitura",
    "flashcard_review": "Revisar flashcards",
    "material_review": "Revisar material",
    "correction_review": "Revisar correção",
    "other": "Outro",
}

TASK_CATEGORY_ALIASES = {
    "assistir aula": "watch_lesson",
    "watch_lesson": "watch_lesson",
    "revisar aula": "review_lesson",
    "review_lesson": "review_lesson",
    "fazer exercicios": "do_exercises",
    "exercicios": "do_exercises",
    "do_exercises": "do_exercises",
    "redacao": "essay",
    "essay": "essay",
    "simulado": "mock_exam",
    "mock_exam": "mock_exam",
    "trabalho escolar": "school_work",
    "school_work": "school_work",
    "leitura": "reading",
    "reading": "reading",
    "flashcards": "flashcard_review",
    "flashcard_review": "flashcard_review",
    "revisao de material": "material_review",
    "material_review": "material_review",
    "correcao": "correction_review",
    "correction_review": "correction_review",
    "outro": "other",
    "other": "other",
}

STATUS_LABELS = {
    "pending": "Pendente",
    "completed": "Concluída",
    "late": "Atrasada",
    "rescheduled": "Reagendada",
}

STATUS_ALIASES = {
    "pending": "pending",
    "pendente": "pending",
    "completed": "completed",
    "concluida": "completed",
    "late": "late",
    "atrasada": "late",
    "rescheduled": "rescheduled",
    "reagendada": "rescheduled",
}

ROUTINE_TYPE_LABELS = {
    "school": "Escola",
    "course": "Cursinho",
    "transport": "Transporte",
    "work": "Trabalho",
    "sleep": "Sono",
    "rest": "Descanso",
    "personal": "Pessoal",
    "study_window": "Janela de estudo",
    "other": "Outro",
}

ROUTINE_TYPE_ALIASES = {
    "escola": "school",
    "school": "school",
    "cursinho": "course",
    "course": "course",
    "curso": "course",
    "transporte": "transport",
    "transport": "transport",
    "trabalho": "work",
    "work": "work",
    "estagio": "work",
    "sono": "sleep",
    "sleep": "sleep",
    "descanso": "rest",
    "rest": "rest",
    "pessoal": "personal",
    "personal": "personal",
    "estudo": "study_window",
    "janela de estudo": "study_window",
    "study_window": "study_window",
    "outro": "other",
    "other": "other",
}

MATERIAL_TYPE_LABELS = {
    "pdf": "PDF",
    "text": "Texto",
    "docx": "DOCX",
    "image": "Imagem",
    "slides": "Slides",
    "exercise_list": "Lista de exercícios",
    "essay_correction": "Correção de redação",
    "schedule": "Cronograma",
    "notes": "Anotações",
    "other": "Outro",
}

MATERIAL_TYPE_ALIASES = {
    "pdf": "pdf",
    "texto": "text",
    "text": "text",
    "docx": "docx",
    "imagem": "image",
    "image": "image",
    "slides": "slides",
    "lista": "exercise_list",
    "lista de exercicios": "exercise_list",
    "exercise_list": "exercise_list",
    "correcao": "essay_correction",
    "essay_correction": "essay_correction",
    "cronograma": "schedule",
    "schedule": "schedule",
    "aula": "notes",
    "anotacoes": "notes",
    "notes": "notes",
    "edital": "other",
    "outro": "other",
    "other": "other",
}


def key(value: str | None) -> str:
    text = (value or "").strip().lower()
    if "Ã" in text or "Â" in text:
        try:
            text = text.encode("latin1").decode("utf-8")
        except UnicodeError:
            pass
    text = "".join(char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip()


def normalize_source(value: str | None, default: str = "personal") -> str:
    return SOURCE_ALIASES.get(key(value), default)


def normalize_task_category(value: str | None, default: str = "other") -> str:
    return TASK_CATEGORY_ALIASES.get(key(value), default)


def normalize_status(value: str | None, default: str = "pending") -> str:
    return STATUS_ALIASES.get(key(value), default)


def normalize_routine_type(value: str | None, default: str = "other") -> str:
    return ROUTINE_TYPE_ALIASES.get(key(value), default)


def normalize_material_type(value: str | None, default: str = "other") -> str:
    return MATERIAL_TYPE_ALIASES.get(key(value), default)


def label(mapping: dict[str, str], value: str | None) -> str:
    return mapping.get(value or "", value or "")
