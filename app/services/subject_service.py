from sqlalchemy.orm import Session

from app.models import Subject, SubjectFront


DEFAULT_SUBJECTS = [
    ("Matemática", "Matemática", "#3b82f6", ["Álgebra", "Geometria", "Funções", "Probabilidade"]),
    ("Física", "Ciências da Natureza", "#06b6d4", ["Mecânica", "Eletricidade", "Ondulatória", "Termologia"]),
    ("Química", "Ciências da Natureza", "#14b8a6", ["Química Geral", "Físico-Química", "Química Orgânica", "Química Ambiental", "Química Inorgânica"]),
    ("Biologia", "Ciências da Natureza", "#22c55e", ["Ecologia", "Genética", "Citologia", "Fisiologia"]),
    ("História", "Ciências Humanas", "#f97316", ["História do Brasil", "História Geral", "Contemporânea"]),
    ("Geografia", "Ciências Humanas", "#84cc16", ["Geografia Física", "Geopolítica", "Urbanização"]),
    ("Filosofia", "Ciências Humanas", "#a855f7", ["Ética", "Política", "Epistemologia"]),
    ("Sociologia", "Ciências Humanas", "#ec4899", ["Cultura", "Trabalho", "Poder"]),
    ("Português", "Linguagens", "#6366f1", ["Gramática", "Interpretação", "Variação linguística"]),
    ("Literatura", "Linguagens", "#8b5cf6", ["Escolas literárias", "Obras obrigatórias", "Poesia"]),
    ("Redação", "Redação", "#ef4444", ["Projeto de texto", "Argumentação", "Intervenção"]),
    ("Inglês", "Linguagens", "#0ea5e9", ["Leitura", "Vocabulário", "Interpretação"]),
    ("Espanhol", "Linguagens", "#f59e0b", ["Leitura", "Vocabulário", "Interpretação"]),
]

TECHNICAL_SUBJECTS = [
    "Materiais de Construção",
    "Desenho Técnico",
    "Topografia",
    "Estruturas",
    "Instalações Prediais",
]


def ensure_default_subjects(user_id: int, db: Session, include_technical: bool = False) -> None:
    existing = {item.name.lower(): item for item in db.query(Subject).filter(Subject.user_id == user_id).all()}
    for name, area, color, fronts in DEFAULT_SUBJECTS:
        subject = existing.get(name.lower())
        if not subject:
            subject = Subject(user_id=user_id, name=name, area=area, source_type="vestibular", color=color)
            db.add(subject)
            db.flush()
        _ensure_fronts(subject.id, fronts, db)

    if include_technical:
        for index, name in enumerate(TECHNICAL_SUBJECTS):
            if name.lower() not in existing:
                db.add(
                    Subject(
                        user_id=user_id,
                        name=name,
                        area="Curso Técnico",
                        source_type="technical_course",
                        color=["#64748b", "#0891b2", "#0f766e", "#7c3aed", "#b45309"][index % 5],
                    )
                )
    db.commit()


def find_or_create_subject(user_id: int, name: str | None, db: Session, *, area: str = "Outros", source_type: str = "personal") -> Subject | None:
    clean = (name or "").strip()
    if not clean:
        return None
    subject = db.query(Subject).filter(Subject.user_id == user_id, Subject.name.ilike(clean)).first()
    if subject:
        return subject
    subject = Subject(user_id=user_id, name=clean[:120], area=area, source_type=source_type)
    db.add(subject)
    db.flush()
    return subject


def subject_dict(subject: Subject) -> dict[str, object]:
    return {
        "id": subject.id,
        "name": subject.name,
        "area": subject.area,
        "source_type": subject.source_type,
        "color": subject.color,
        "is_active": subject.is_active,
        "description": subject.description,
        "fronts": [
            {"id": front.id, "name": front.name, "description": front.description, "order": front.order}
            for front in sorted(subject.fronts, key=lambda item: item.order)
        ],
    }


def _ensure_fronts(subject_id: int, front_names: list[str], db: Session) -> None:
    existing = {front.name.lower() for front in db.query(SubjectFront).filter(SubjectFront.subject_id == subject_id).all()}
    for order, name in enumerate(front_names):
        if name.lower() not in existing:
            db.add(SubjectFront(subject_id=subject_id, name=name, order=order))
