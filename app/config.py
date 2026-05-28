import os
from importlib import import_module
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def _private_secret(name: str, default: str = "") -> str:
    try:
        module = import_module("app.private_ai_keys")
    except ModuleNotFoundError:
        return default
    return str(getattr(module, name, default) or default)


class Settings:
    app_name: str = os.getenv("APP_NAME", "AprovaOS")
    app_env: str = os.getenv("APP_ENV", "development")
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./aprovaos.db")
    upload_dir: Path = Path(os.getenv("UPLOAD_DIR", "uploads")).resolve()
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "10"))
    session_cookie: str = os.getenv("SESSION_COOKIE", "aprovaos_session")
    allowed_upload_extensions: set[str] = {".pdf", ".txt", ".md", ".png", ".jpg", ".jpeg", ".docx", ".pptx"}
    ai_provider: str = os.getenv("AI_PROVIDER", "openai")
    ai_mock_mode: bool = os.getenv("AI_MOCK_MODE", "false").lower() == "true"
    ai_api_key: str = os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY") or _private_secret("OPENAI_API_KEY")
    ai_model: str = os.getenv("OPENAI_MODEL") or os.getenv("AI_MODEL", "gpt-4.1-mini")
    ai_base_url: str = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    ai_timeout_seconds: float = float(os.getenv("AI_TIMEOUT_SECONDS", "30"))
    ai_data_training_enabled: bool = os.getenv("AI_DATA_TRAINING_ENABLED", "false").lower() == "true"
    ai_internal_keys_only: bool = os.getenv("AI_INTERNAL_KEYS_ONLY", "true").lower() == "true"
    ai_settings_ui_enabled: bool = os.getenv("AI_SETTINGS_UI_ENABLED", "false").lower() == "true"
    ai_ensemble_enabled: bool = os.getenv("AI_ENSEMBLE_ENABLED", "true").lower() == "true"
    ai_ensemble_synthesis_provider: str = os.getenv("AI_ENSEMBLE_SYNTHESIS_PROVIDER", "openai").lower().strip()
    ai_keys_master_secret: str = os.getenv("AI_KEYS_MASTER_SECRET") or os.getenv("FERNET_SECRET_KEY") or _private_secret("AI_KEYS_MASTER_SECRET")
    ai_default_provider: str = os.getenv("AI_DEFAULT_PROVIDER", os.getenv("AI_PROVIDER", "openai")).lower().strip()
    ai_default_model: str = os.getenv("AI_DEFAULT_MODEL", os.getenv("OPENAI_MODEL") or os.getenv("AI_MODEL", "gpt-4.1-mini"))
    openai_api_key: str = os.getenv("OPENAI_API_KEY") or os.getenv("AI_API_KEY") or _private_secret("OPENAI_API_KEY")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY") or _private_secret("GEMINI_API_KEY")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY") or _private_secret("DEEPSEEK_API_KEY")
    admin_emails: set[str] = {
        item.strip().lower()
        for item in os.getenv("ADMIN_EMAILS", "").split(",")
        if item.strip()
    }
    google_client_id: str = os.getenv("GOOGLE_CALENDAR_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv("GOOGLE_CALENDAR_REDIRECT_URI", "http://127.0.0.1:8000/api/calendar/google/callback")
    ollama_enabled: bool = os.getenv("OLLAMA_ENABLED", "false").lower() == "true"
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3")


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
