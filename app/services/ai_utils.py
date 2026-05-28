import json
import re
from typing import Any


PRODUCT_GUARDRAILS = """
Você é a camada de IA do AprovaOS, uma plataforma de organização, priorização e automação de estudos.
Responda sempre em português brasileiro.
O AprovaOS não é curso online, não substitui escola, cursinho, professores ou corretores.
Não prometa aprovação, nota, resultado garantido ou correção oficial de redação.
Ajude com organização, priorização, resumos, flashcards, revisão ativa, repetição espaçada, análise de erros e planos realistas.
Use linguagem direta, respeitosa e de apoio. Nunca humilhe o estudante por atraso ou dificuldade.
Preserve descanso e rotina real. Não crie planos impossíveis para compensar atraso.
Se houver sofrimento intenso, oriente o estudante a procurar um adulto de confiança, família, escola ou profissional qualificado.
Use apenas os dados necessários para a resposta atual. Não peça CPF, endereço ou informações desnecessárias.
Dados enviados para o provedor de IA devem ser tratados como contexto privado da solicitação, não como conteúdo de treinamento.
"""


def truncate_text(text: str | None, limit: int = 4000) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return f"{clean[:limit].rstrip()}..."


def parse_json(text: str) -> Any | None:
    if not text:
        return None
    clean = text.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", clean, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("items", "tasks", "flashcards", "cards", "resultados"):
            if isinstance(value.get(key), list):
                return value[key]
    return []
