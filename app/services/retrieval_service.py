import re

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Material
from app.services.ai_utils import truncate_text


def search_materials(user_id: int, query: str, db: Session, limit: int = 20) -> list[Material]:
    clean = (query or "").strip()
    base = db.query(Material).filter(Material.user_id == user_id)
    if clean:
        like = f"%{clean}%"
        base = base.filter(
            or_(
                Material.title.ilike(like),
                Material.subject.ilike(like),
                Material.topic.ilike(like),
                Material.subtopic.ilike(like),
                Material.tags.ilike(like),
                Material.source.ilike(like),
                Material.source_type.ilike(like),
                Material.extracted_text.ilike(like),
            )
        )
    return base.order_by(Material.created_at.desc()).limit(limit).all()


def relevant_material_chunks(user_id: int, query: str, db: Session, limit: int = 4) -> list[dict[str, object]]:
    terms = [term for term in re.findall(r"\w+", (query or "").lower()) if len(term) > 3]
    materials = db.query(Material).filter(Material.user_id == user_id, Material.extracted_text.isnot(None)).order_by(Material.created_at.desc()).limit(20).all()

    def score(material: Material) -> int:
        haystack = f"{material.title} {material.subject or ''} {material.topic or ''} {material.extracted_text or ''}".lower()
        return sum(haystack.count(term) for term in terms)

    chunks = []
    for material in sorted(materials, key=score, reverse=True)[:limit]:
        text = material.extracted_text or material.ai_summary or material.summary or ""
        section = _section_for_text(text, terms)
        chunks.append(
            {
                "material_id": material.id,
                "title": material.title,
                "section": section["section"],
                "excerpt": section["excerpt"],
            }
        )
    return chunks


def _section_for_text(text: str, terms: list[str]) -> dict[str, str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return {"section": "Trecho principal", "excerpt": ""}
    index = 0
    for i, line in enumerate(lines):
        lower = line.lower()
        if any(term in lower for term in terms):
            index = i
            break
    section = "Trecho relevante"
    for candidate in reversed(lines[: index + 1]):
        if 3 <= len(candidate) <= 90 and not candidate.endswith("."):
            section = candidate.strip("#: ")
            break
    excerpt = truncate_text(" ".join(lines[max(0, index - 1) : min(len(lines), index + 4)]), 900)
    return {"section": section, "excerpt": excerpt}
