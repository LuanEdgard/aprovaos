import re
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.config import settings


ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "image/png",
    "image/jpeg",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/octet-stream",
}


def safe_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in settings.allowed_upload_extensions:
        raise HTTPException(status_code=400, detail="Tipo de arquivo não permitido para este MVP.")
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(filename).stem).strip("-") or "material"
    return f"{stem}-{uuid4().hex[:10]}{suffix}"


def save_uploaded_file(file: UploadFile) -> Path:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo sem nome.")
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="Tipo MIME não permitido para este MVP.")

    filename = safe_filename(file.filename)
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


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return extract_text_from_txt(path)
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    return ""


def extract_text_from_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")[:120000]


def extract_text_from_pdf(path: Path) -> str:
    try:
        import fitz
    except ImportError:
        return ""

    text_chunks: list[str] = []
    with fitz.open(path) as doc:
        for page in doc[:40]:
            text_chunks.append(page.get_text())
    return "\n".join(text_chunks)[:120000]
