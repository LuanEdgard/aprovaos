from app.services.providers.openai_provider import OpenAIProvider


class DeepSeekProvider(OpenAIProvider):
    provider_name = "deepseek"

    def __init__(self, api_key: str, model: str, *, base_url: str = "https://api.deepseek.com/v1", timeout: float | None = None) -> None:
        super().__init__(api_key, model, base_url=base_url, timeout=timeout)
