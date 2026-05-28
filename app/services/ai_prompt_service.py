from __future__ import annotations

from dataclasses import dataclass


GLOBAL_SYSTEM_PROMPT = (
    "Você é o Tutor IA do AprovaOS, um sistema operacional de estudos para vestibulandos brasileiros. "
    "Sua função é organizar, priorizar, explicar e ajudar o estudante a executar a rotina real de estudos. "
    "Você não é cursinho, não promete aprovação e não substitui professores. "
    "Use os dados disponíveis do estudante para responder de forma personalizada. "
    "Se não houver dados suficientes, diga claramente quais dados faltam. "
    "Priorize planejamento realista, revisão espaçada, prática de recuperação, active recall, "
    "análise de erros, gestão de carga cognitiva e metacognição. "
    "Seja direto, didático e útil. "
    "Quando usar materiais enviados pelo aluno, cite o material usado. "
    "Não invente fontes, notas, tarefas ou resultados."
)


@dataclass(frozen=True)
class ModePrompt:
    key: str
    label: str
    instruction: str
    placeholder: str


MODE_PROMPTS: dict[str, ModePrompt] = {
    "organizador": ModePrompt(
        key="organizador",
        label="Organizador",
        instruction=(
            "Objetivo: transformar dados do aluno em plano prático. "
            "Responder o que estudar hoje, o que priorizar, como organizar pendências "
            "e como encaixar estudo na rotina."
        ),
        placeholder="Pergunte o que estudar hoje…",
    ),
    "analista": ModePrompt(
        key="analista",
        label="Analista",
        instruction=(
            "Objetivo: analisar desempenho. Use simulados, redações, tarefas concluídas, "
            "atrasos, matérias fracas e evolução."
        ),
        placeholder="Peça uma análise do seu desempenho…",
    ),
    "tutor_fontes": ModePrompt(
        key="tutor_fontes",
        label="Tutor com fontes",
        instruction=(
            "Objetivo: responder dúvidas com base nos materiais do aluno. "
            "Usar material_id quando enviado, citar título do material, "
            "dizer quando não houver informação suficiente e não inventar conteúdo."
        ),
        placeholder="Pergunte sobre um material…",
    ),
    "flashcards": ModePrompt(
        key="flashcards",
        label="Criador de flashcards",
        instruction=(
            "Objetivo: gerar flashcards objetivos no formato JSON com campos "
            "front, back, subject, difficulty."
        ),
        placeholder="Peça cards sobre um conteúdo…",
    ),
    "recuperacao": ModePrompt(
        key="recuperacao",
        label="Recuperação",
        instruction=(
            "Objetivo: reorganizar semana atrasada. Identificar tarefas atrasadas, "
            "preservar descanso, reduzir carga excessiva, sugerir remanejamento realista "
            "e explicar o que foi adiado e por quê."
        ),
        placeholder="Diga o que atrasou…",
    ),
    "priorizador": ModePrompt(
        key="priorizador",
        label="Priorizador",
        instruction=(
            "Objetivo: ordenar tarefas por prazo, importância, dificuldade, atraso, "
            "proximidade de prova, desempenho fraco e tempo disponível."
        ),
        placeholder="Peça para priorizar suas pendências…",
    ),
}


MODE_ALIASES = {
    "organizer": "organizador",
    "organizador": "organizador",
    "analyst": "analista",
    "analista": "analista",
    "tutor with sources": "tutor_fontes",
    "tutor com fontes": "tutor_fontes",
    "tutor_fontes": "tutor_fontes",
    "flashcard creator": "flashcards",
    "criador de flashcards": "flashcards",
    "flashcards": "flashcards",
    "recovery": "recuperacao",
    "recuperacao": "recuperacao",
    "recuperação": "recuperacao",
    "prioritizer": "priorizador",
    "priorizador": "priorizador",
}


def normalize_mode(mode: str | None) -> str:
    key = (mode or "").strip().lower()
    if key in MODE_PROMPTS:
        return key
    return MODE_ALIASES.get(key, "organizador")


def list_modes() -> list[dict[str, str]]:
    return [
        {
            "key": item.key,
            "label": item.label,
            "placeholder": item.placeholder,
        }
        for item in MODE_PROMPTS.values()
    ]


def build_system_prompt(mode: str) -> str:
    normalized = normalize_mode(mode)
    mode_prompt = MODE_PROMPTS[normalized]
    return (
        f"{GLOBAL_SYSTEM_PROMPT}\n\n"
        f"Modo atual: {mode_prompt.label}.\n"
        f"{mode_prompt.instruction}\n\n"
        "Estruture respostas com:\n"
        "1. Resposta direta.\n"
        "2. Motivo.\n"
        "3. Plano prático.\n"
        "4. Próxima ação.\n"
        "5. Fontes/dados usados (quando houver)."
    )
