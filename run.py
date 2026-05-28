import os

try:
    import uvicorn
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Dependência ausente: uvicorn. Instale com `pip install -r requirements.txt` "
        "e tente novamente."
    ) from exc


if __name__ == "__main__":
    reload_enabled = os.getenv("APP_RELOAD", "false").lower() == "true"
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=reload_enabled,
        reload_dirs=["app"] if reload_enabled else None,
    )
