import re
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Material
from app.services.ai_gateway import AIGateway, parse_gateway_json
from app.services.ai_utils import as_list, truncate_text
from app.services.flashcard_engine import generate_flashcards_from_text


SUBJECT_HINTS = {
    "matemática": ["função", "equação", "geometria", "probabilidade", "logaritmo"],
    "redação": ["tese", "repertório", "competência", "intervenção", "argumento"],
    "biologia": ["célula", "ecologia", "genética", "evolução", "organismo"],
    "química": ["mol", "reação", "ácido", "base", "estequiometria"],
    "física": ["força", "energia", "velocidade", "campo", "movimento"],
    "história": ["república", "revolução", "império", "colonial", "guerra"],
    "geografia": ["clima", "relevo", "urbanização", "globalização", "território"],
    "português": ["texto", "linguagem", "literatura", "interpretação", "gramática"],
}


def _safe_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in settings.allowed_upload_extensions:
        raise HTTPException(status_code=400, detail="Tipo de arquivo não permitido para este MVP.")
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(filename).stem).strip("-") or "material"
    return f"{stem}-{uuid4().hex[:10]}{suffix}"


def save_uploaded_file(file: UploadFile) -> Path:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo sem nome.")

    filename = _safe_filename(file.filename)
    destination = (settings.upload_dir / filename).resolve()
    if settings.upload_dir not in destination.parents and destination.parent != settings.upload_dir:
        raise HTTPException(status_code=400, detail="Caminho de upload inválido.")

    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if destination.stat().st_size > max_bytes:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"O arquivo excede {settings.max_upload_mb} MB.")
    return destination


def extract_text_from_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")[:50000]


def extract_text_from_pdf_if_possible(path: Path) -> str:
    try:
        import fitz
    except ImportError:
        return ""

    text_chunks: list[str] = []
    with fitz.open(path) as doc:
        for page in doc[:8]:
            text_chunks.append(page.get_text())
    return "\n".join(text_chunks)[:50000]


def summarize_text(text: str, title: str = "Material", subject: str | None = None, *, user_id: int | None = None, db: Session | None = None) -> str:
    clean_text = " ".join((text or "").split())
    if not clean_text:
        return "Resumo indisponível: ainda não há texto extraído ou colado para este material."

    if db:
        prompt = f"""
        Material: {title}
        Matéria informada: {subject or "não informada"}
        Texto do material:
        {truncate_text(clean_text, 9000)}
        """
        response = AIGateway(db, user_id).summarize_material(
            "Gere um resumo de estudo para um material enviado ao AprovaOS. "
            "Não transforme em aula completa. Foque em organização, pontos-chave, revisão ativa e próximos passos. "
            "JSON esperado: summary, key_points, active_recall_questions, suggested_next_steps.",
            prompt,
            max_tokens=1400,
        )
        if response.used_ai and isinstance(response.data, dict):
            return _format_ai_summary(response.data)

    sentences = [item.strip() for item in re.split(r"[.!?]\s+", clean_text) if item.strip()]
    summary = ". ".join(sentences[:4])
    if len(sentences) > 4:
        summary += "."
    return f"IA não configurada. Resumo básico gerado localmente: {summary[:1100]}"


def detect_subject_from_text(text: str) -> str:
    lower = (text or "").lower()
    scores = {
        subject: sum(1 for hint in hints if hint in lower)
        for subject, hints in SUBJECT_HINTS.items()
    }
    best_subject, best_score = max(scores.items(), key=lambda item: item[1])
    return best_subject if best_score else "geral"


def generate_tasks_from_material(material: Material, *, user_id: int | None = None, db: Session | None = None) -> list[dict[str, object]]:
    subject = material.subject or detect_subject_from_text(material.extracted_text or "")
    clean_text = " ".join((material.extracted_text or material.summary or "").split())
    if clean_text and db:
        prompt = f"""
        Título: {material.title}
        Tipo: {material.material_type}
        Fonte: {material.source_type}
        Matéria: {subject}
        Texto:
        {truncate_text(clean_text, 8500)}

        Crie no máximo 6 pendências realistas para estudar esse material.
        Use tarefas curtas, acionáveis e sem sobrecarregar o estudante.
        """
        response = AIGateway(db, user_id or material.user_id).generate_json(
            "materials",
            "generate_tasks_from_material",
            "Gere pendências de estudo para o AprovaOS. "
            "Não crie tarefas de curso completo. Use revisão ativa, leitura orientada, questões e flashcards quando fizer sentido. "
            "JSON esperado: {\"tasks\": [{\"title\": string, \"subject\": string, \"source_type\": string, "
            "\"priority\": \"alta|média|baixa\", \"estimated_minutes\": number, \"days_from_now\": number}]}",
            prompt,
            max_tokens=1200,
        )
        tasks = [_sanitize_ai_task(item, material, subject) for item in as_list(response.data)]
        tasks = [task for task in tasks if task]
        if tasks:
            return tasks[:6]

    return [
        {
            "title": f"Ler e marcar pontos-chave: {material.title}",
            "subject": subject,
            "source_type": material.source_type,
            "priority": "média",
            "estimated_minutes": 40,
            "material_id": material.id,
        },
        {
            "title": f"Fazer revisão ativa do material: {material.title}",
            "subject": subject,
            "source_type": "revisão",
            "priority": "alta",
            "estimated_minutes": 30,
            "material_id": material.id,
        },
    ]


def generate_flashcards_from_material(material: Material, *, user_id: int | None = None, db: Session | None = None) -> list[dict[str, str]]:
    clean_text = " ".join((material.extracted_text or material.summary or "").split())
    if clean_text and db:
        prompt = f"""
You are an assistant specialized in converting study materials such as PDFs, slides, notes, and pasted text into BASIC flashcards for Brazilian vestibular exams such as FUVEST, ENEM, COMVEST, and Poliedro.

MANDATORY RULES:

1. Use only BASIC flashcards:
- front: question
- back: answer
- tag: Vestibular::Area::Subject::Content

2. Minimum information principle:
- Each flashcard must test only one classic fact directly likely to appear in exams.
- The question must have one clear answer.
- The answer must be short, preferably one word or one short sentence.
- If the content needs multiple answers, split it into multiple cards.
- Do not include long explanations in the answer.

3. Format:
- Front: direct question, up to 40 words.
- Back: objective and short answer.
- Tag example:
  ENEM/FUVEST/COMVEST::Ciências_Humanas::História_do_Brasil::Período_Colonial

4. Language and style:
- Use Brazilian Portuguese.
- Use exam-like style for USP, FUVEST, ENEM, COMVEST, and Poliedro.
- Avoid “explain”, “discuss”, “comment”.
- Avoid open-ended, subjective, interpretive questions.
- Avoid rare curiosities or details unlikely to be tested.

5. Allowed question types:
- Qual a definição de...
- O que é...
- Qual a principal característica de...
- Qual a principal fórmula de...
- Qual o agente morfológico de...
- Qual a tríade de...
- Qual o principal problema de...
- Qual é o tipo mais comum de...

6. Exclusion criteria:
Do not generate a flashcard if:
- there is no single correct answer
- the content is vague or opinion-based
- the content requires a discursive answer
- the content is not classic exam content

7. Output:
Return JSON only, with this structure:
[
  {{
    "front": "...",
    "back": "...",
    "tag": "..."
  }}
]

8. Quantity:
Generate between 5 and 20 cards per batch unless the user requests another quantity.

9. Accuracy:
Prioritize precision, objectivity, and fast recall.

Título do material: {material.title}
Matéria: {material.subject or "geral"}
Texto:
{truncate_text(clean_text, 8500)}
        """
        response = AIGateway(db, user_id or material.user_id).generate_flashcards(
            "Converta material em flashcards básicos. Responda somente com JSON array válido, sem markdown.",
            prompt,
            max_tokens=1600,
        )
        parsed = parse_gateway_json(response) if response.used_ai else None
        cards = [_sanitize_ai_card(item) for item in as_list(parsed)]
        cards = [card for card in cards if card]
        if cards:
            return cards[:12]

    return generate_flashcards_from_text(material.extracted_text or material.summary or material.title)


def _format_ai_summary(data: dict[str, Any]) -> str:
    parts: list[str] = []
    summary = str(data.get("summary") or "").strip()
    if summary:
        parts.append(summary[:1000])

    key_points = as_list(data.get("key_points"))
    if key_points:
        parts.append("Pontos-chave:")
        parts.extend(f"- {truncate_text(str(item), 180)}" for item in key_points[:6])

    questions = as_list(data.get("active_recall_questions"))
    if questions:
        parts.append("Perguntas de revisão ativa:")
        parts.extend(f"- {truncate_text(str(item), 180)}" for item in questions[:4])

    next_steps = as_list(data.get("suggested_next_steps"))
    if next_steps:
        parts.append("Próximos passos sugeridos:")
        parts.extend(f"- {truncate_text(str(item), 180)}" for item in next_steps[:4])

    return "\n".join(parts).strip()[:2200] or "Resumo gerado, mas a resposta veio sem conteúdo suficiente."


def _sanitize_ai_task(item: Any, material: Material, subject: str) -> dict[str, object] | None:
    if not isinstance(item, dict):
        return None
    title = truncate_text(str(item.get("title") or ""), 170)
    if len(title) < 4:
        return None
    priority = str(item.get("priority") or "média").lower().strip()
    if priority not in {"alta", "média", "baixa"}:
        priority = "média"
    source_type = str(item.get("source_type") or material.source_type or "pessoal").lower().strip()
    if source_type not in {"school", "course", "vestibular", "personal", "technical_course", "other", "escola", "cursinho", "redação", "simulado", "revisão", "pessoal", "enem"}:
        source_type = material.source_type or "pessoal"
    try:
        estimated_minutes = int(item.get("estimated_minutes") or 40)
    except (TypeError, ValueError):
        estimated_minutes = 40
    estimated_minutes = min(max(15, estimated_minutes), 120)
    try:
        days_from_now = int(item.get("days_from_now") or 3)
    except (TypeError, ValueError):
        days_from_now = 3
    return {
        "title": title,
        "subject": truncate_text(str(item.get("subject") or subject or "geral"), 90),
        "source_type": source_type,
        "priority": priority,
        "estimated_minutes": estimated_minutes,
        "deadline": date.today() + timedelta(days=min(max(days_from_now, 1), 14)),
        "material_id": material.id,
    }


def _sanitize_ai_card(item: Any) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    front = truncate_text(str(item.get("front") or ""), 260)
    back = truncate_text(str(item.get("back") or ""), 700)
    if len(front) < 8 or len(back) < 8:
        return None
    return {
        "topic": truncate_text(str(item.get("topic") or "Revisão ativa"), 130),
        "front": front,
        "back": back,
        "tag": truncate_text(str(item.get("tag") or ""), 255),
    }
