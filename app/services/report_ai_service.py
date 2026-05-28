from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.ai_gateway import AIGateway, AIResponse
from app.services.ai_prompt_service import build_system_prompt


class ReportAIService:
    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id
        self.gateway = AIGateway(db, user_id)

    def generate_weekly_insights(self, weekly_report: dict[str, Any], context_counts: dict[str, int]) -> AIResponse:
        return self.gateway.generate_text(
            "reports",
            "weekly_insights",
            build_system_prompt("analista")
            + "\nFoco adicional: gerar insights semanais acionáveis, sem promessas de aprovação.",
            (
                "Relatório semanal estruturado:\n"
                f"{weekly_report}\n\n"
                f"Contagem de contexto disponível: {context_counts}\n\n"
                "Gere análise curta com: gargalos, riscos, plano prático da próxima semana e próxima ação concreta."
            ),
            max_tokens=900,
        )
