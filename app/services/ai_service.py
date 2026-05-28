from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Flashcard, Material, StudyTask
from app.services.ai_context_service import AIContextService
from app.services.ai_gateway import AIGateway
from app.services.ai_prompt_service import build_system_prompt, normalize_mode
from app.services.ai_utils import as_list, truncate_text
from app.services.flashcard_ai_service import FlashcardAIService
from app.services.material_ai_service import MaterialAIService
from app.services.report_ai_service import ReportAIService
from app.services.study_planner_service import StudyPlannerService


MODE_TO_MODULE = {
    "organizador": "planning",
    "analista": "reports",
    "tutor_fontes": "tutor",
    "flashcards": "flashcards",
    "recuperacao": "recovery",
    "priorizador": "planning",
}


@dataclass
class AIServiceError(Exception):
    message: str
    code: str = "AI_PROVIDER_NOT_CONFIGURED"

    def __str__(self) -> str:
        return self.message


class AIService:
    def __init__(self, db: Session, user_id: int) -> None:
        self.db = db
        self.user_id = user_id
        self.gateway = AIGateway(db, user_id)
        self.context_service = AIContextService(db)
        self.material_service = MaterialAIService(db, user_id)
        self.flashcard_service = FlashcardAIService(db, user_id)
        self.planner_service = StudyPlannerService(db, user_id)
        self.report_service = ReportAIService(db, user_id)
        self.mock_mode = bool(settings.ai_mock_mode and settings.app_env.lower() != "production")

    def chat(
        self,
        user_id: int,
        message: str,
        mode: str,
        conversation_id: int | None = None,
        material_id: int | None = None,
    ) -> dict[str, Any]:
        _ = conversation_id
        self._assert_user(user_id)
        ai_configured = self._ai_configured()
        if not ai_configured and not self.mock_mode:
            raise AIServiceError("A IA ainda não foi configurada no servidor.")
        normalized_mode = normalize_mode(mode)
        context = self.context_service.build_student_context(user_id)
        material = self.context_service.material_for_user(user_id, material_id)
        missing = self._missing_data_for_mode(normalized_mode, context, material)
        if not ai_configured and self.mock_mode:
            return self._response(
                answer=self._mock_chat_response(normalized_mode, context, message, material),
                mode=normalized_mode,
                context=context,
                sources=self._sources_for_context(context, material),
                actions=self._default_actions(normalized_mode, material_id, context),
                used_ai=False,
                warning="Modo simulado: a IA real ainda não está conectada.",
                mock_mode=True,
            )
        if missing:
            return self._response(
                answer=(
                    "Ainda faltam dados para personalizar com precisão. "
                    f"Dados necessários agora: {', '.join(missing)}."
                ),
                mode=normalized_mode,
                context=context,
                sources=self._sources_for_context(context, material),
                actions=self._default_actions(normalized_mode, material_id, context),
                used_ai=False,
            )

        system_prompt = build_system_prompt(normalized_mode)
        user_prompt = self._chat_prompt(message, context, material)
        ai_response = self.gateway.generate_text(
            MODE_TO_MODULE[normalized_mode],
            "chat",
            system_prompt,
            user_prompt,
            max_tokens=1300,
        )
        if ai_response.used_ai and ai_response.text:
            return self._response(
                answer=ai_response.text,
                mode=normalized_mode,
                context=context,
                sources=self._sources_for_context(context, material),
                actions=self._default_actions(normalized_mode, material_id, context),
                used_ai=True,
                provider=ai_response.provider_name,
                model=ai_response.model,
            )

        if self.mock_mode:
            return self._response(
                answer=self._mock_chat_response(normalized_mode, context, message, material),
                mode=normalized_mode,
                context=context,
                sources=self._sources_for_context(context, material),
                actions=self._default_actions(normalized_mode, material_id, context),
                used_ai=False,
                warning="Modo simulado: a IA real ainda não está conectada.",
                mock_mode=True,
            )

        raise AIServiceError(
            ai_response.friendly_message or "A IA ainda não foi configurada no servidor.",
            code=ai_response.error_code or "AI_PROVIDER_NOT_CONFIGURED",
        )

    def reorganize_week(self, user_id: int) -> dict[str, Any]:
        self._assert_user(user_id)
        ai_configured = self._ai_configured()
        if not ai_configured and not self.mock_mode:
            raise AIServiceError("A IA ainda não foi configurada no servidor.")
        context = self.context_service.build_student_context(user_id)
        preview = self.planner_service.preview_reorganize_week()
        if not preview.get("preview"):
            return self._response(
                answer="Não há pendências atrasadas para reorganizar agora.",
                mode="recuperacao",
                context=context,
                sources=self._sources_for_context(context, None),
                actions=[],
                used_ai=False,
            )

        ai_response = self.gateway.generate_text(
            "recovery",
            "reorganize_week",
            build_system_prompt("recuperacao"),
            (
                f"Contexto do estudante: {json.dumps(context, ensure_ascii=False, default=str)[:12000]}\n\n"
                f"Preview da reorganização: {preview['preview']}\n"
                "Explique o plano de recuperação de forma objetiva e realista."
            ),
            max_tokens=900,
        )
        answer = (
            ai_response.text
            if ai_response.used_ai and ai_response.text
            else "Plano de recuperação gerado. Revise a prévia e aplique somente o que fizer sentido."
        )
        warning = None
        mock_mode = False
        if not ai_response.used_ai and self.mock_mode:
            answer = "Modo simulado: reorganização em prévia pronta. Revise e aplique quando quiser."
            warning = "Modo simulado: a IA real ainda não está conectada."
            mock_mode = True
        elif not ai_response.used_ai and not self.mock_mode:
            raise AIServiceError(
                ai_response.friendly_message or "A IA ainda não foi configurada no servidor.",
                code=ai_response.error_code or "AI_PROVIDER_NOT_CONFIGURED",
            )

        return self._response(
            answer=answer,
            mode="recuperacao",
            context=context,
            sources=self._sources_for_context(context, None),
            actions=[
                {
                    "label": "Aplicar reorganização",
                    "action": "apply_reorganize_week",
                    "payload": {"preview": preview.get("preview", [])},
                }
            ],
            used_ai=bool(ai_response.used_ai),
            warning=warning,
            mock_mode=mock_mode,
            extra={"preview": preview.get("preview", []), "windows": preview.get("windows", [])},
        )

    def prioritize_tasks(self, user_id: int) -> dict[str, Any]:
        self._assert_user(user_id)
        ai_configured = self._ai_configured()
        if not ai_configured and not self.mock_mode:
            raise AIServiceError("A IA ainda não foi configurada no servidor.")
        context = self.context_service.build_student_context(user_id)
        prioritized = self.planner_service.prioritize(
            context.get("student", {}).get("weekly_priority")
            or context.get("goals", {}).get("weekly_priority")
            or "Equilíbrio"
        )
        ai_response = self.gateway.generate_text(
            "planning",
            "prioritize_tasks",
            build_system_prompt("priorizador"),
            (
                f"Tarefas priorizadas: {prioritized.get('tasks', [])}\n\n"
                f"Contexto resumido: {json.dumps(context.get('counts', {}), ensure_ascii=False)}\n"
                "Explique a priorização com critérios de prazo, impacto e carga real."
            ),
            max_tokens=900,
        )

        if not ai_response.used_ai:
            if self.mock_mode:
                answer = "Modo simulado: priorização estruturada pronta com base nos dados atuais."
                warning = "Modo simulado: a IA real ainda não está conectada."
            elif ai_response.error_code == "AI_PROVIDER_NOT_CONFIGURED":
                raise AIServiceError(
                    ai_response.friendly_message or "A IA ainda não foi configurada no servidor.",
                    code=ai_response.error_code or "AI_PROVIDER_NOT_CONFIGURED",
                )
            else:
                top = prioritized.get("tasks", [])[:5]
                lines = ["IA indisponível no momento. Priorização local baseada nos dados do seu SaaS:"]
                for index, task in enumerate(top, start=1):
                    lines.append(
                        f"{index}. {task.get('title')} ({task.get('priority')}, prazo {task.get('deadline') or 'sem prazo'})"
                    )
                answer = "\n".join(lines)
                warning = ai_response.friendly_message or "A IA real está indisponível no momento."
        else:
            answer = ai_response.text
            warning = None

        return self._response(
            answer=answer,
            mode="priorizador",
            context=context,
            sources=self._sources_for_context(context, None),
            actions=[],
            used_ai=bool(ai_response.used_ai),
            warning=warning,
            mock_mode=bool(warning),
            extra={"prioritized_tasks": prioritized.get("tasks", [])},
        )

    def summarize_material(self, user_id: int, material_id: int) -> dict[str, Any]:
        self._assert_user(user_id)
        ai_configured = self._ai_configured()
        if not ai_configured and not self.mock_mode:
            raise AIServiceError("A IA ainda não foi configurada no servidor.")
        context = self.context_service.build_student_context(user_id)
        material = self._require_material(user_id, material_id)
        prompt_text = self.material_service.content_for_prompt(material, 10000)
        response = self.gateway.generate_text(
            "materials",
            "summarize_material",
            (
                build_system_prompt("tutor_fontes")
                + "\nObjetivo adicional: resumir o material de estudo de forma prática."
            ),
            (
                f"Material selecionado: {self.material_service.material_source(material)}\n\n"
                f"Conteúdo:\n{prompt_text}\n\n"
                "Responda com resumo curto, pontos-chave, plano prático e próxima ação."
            ),
            max_tokens=1100,
        )
        if not response.used_ai:
            if self.mock_mode:
                answer = (
                    "Modo simulado: resumo preliminar com base no conteúdo disponível.\n"
                    f"- Material: {material.title}\n"
                    "- Foque em pontos-chave, depois gere questões de recuperação ativa."
                )
                warning = "Modo simulado: a IA real ainda não está conectada."
            elif response.error_code == "AI_PROVIDER_NOT_CONFIGURED":
                raise AIServiceError(
                    response.friendly_message or "A IA ainda não foi configurada no servidor.",
                    code=response.error_code or "AI_PROVIDER_NOT_CONFIGURED",
                )
            else:
                answer = (
                    "IA indisponível no momento. Resumo local:\n"
                    f"- Material: {material.title}\n"
                    f"- Tema: {material.subject or 'geral'}\n"
                    f"- Trecho base: {truncate_text(prompt_text, 320)}"
                )
                warning = response.friendly_message or "A IA real está indisponível no momento."
        else:
            answer = response.text
            warning = None
        return self._response(
            answer=answer,
            mode="tutor_fontes",
            context=context,
            sources=[{"type": "material", "title": material.title, "id": material.id}],
            actions=[
                {
                    "label": "Gerar flashcards",
                    "action": "prepare_flashcards_from_material",
                    "payload": {"material_id": material.id},
                },
                {
                    "label": "Gerar pendências",
                    "action": "prepare_tasks_from_material",
                    "payload": {"material_id": material.id},
                },
            ],
            used_ai=bool(response.used_ai),
            warning=warning,
            mock_mode=bool(warning),
        )

    def ask_material(self, user_id: int, material_id: int, question: str) -> dict[str, Any]:
        self._assert_user(user_id)
        ai_configured = self._ai_configured()
        if not ai_configured and not self.mock_mode:
            raise AIServiceError("A IA ainda não foi configurada no servidor.")
        if len((question or "").strip()) < 2:
            raise AIServiceError("Informe uma pergunta válida sobre o material.", code="VALIDATION_ERROR")
        context = self.context_service.build_student_context(user_id)
        material = self._require_material(user_id, material_id)
        prompt_text = self.material_service.content_for_prompt(material, 10000)
        response = self.gateway.generate_text(
            "materials",
            "ask_material",
            build_system_prompt("tutor_fontes"),
            (
                f"Pergunta: {question}\n\n"
                f"Material selecionado: {self.material_service.material_source(material)}\n"
                f"Conteúdo:\n{prompt_text}\n\n"
                "Responda apenas com base no material quando possível. "
                "Se faltar dado no material, diga explicitamente."
            ),
            max_tokens=1200,
        )
        if not response.used_ai:
            if self.mock_mode:
                answer = (
                    "Modo simulado: resposta preliminar baseada no contexto local.\n"
                    "A IA real não está conectada para análise semântica completa do material."
                )
                warning = "Modo simulado: a IA real ainda não está conectada."
            elif response.error_code == "AI_PROVIDER_NOT_CONFIGURED":
                raise AIServiceError(
                    response.friendly_message or "A IA ainda não foi configurada no servidor.",
                    code=response.error_code or "AI_PROVIDER_NOT_CONFIGURED",
                )
            else:
                answer = (
                    "IA indisponível no momento. Resposta local baseada no material selecionado:\n"
                    f"- Material: {material.title}\n"
                    f"- Pergunta: {question}\n"
                    "- Sugestão: use os tópicos do material para montar resposta curta e validar com exercícios."
                )
                warning = response.friendly_message or "A IA real está indisponível no momento."
        else:
            answer = response.text
            warning = None
        return self._response(
            answer=answer,
            mode="tutor_fontes",
            context=context,
            sources=[{"type": "material", "title": material.title, "id": material.id}],
            actions=[],
            used_ai=bool(response.used_ai),
            warning=warning,
            mock_mode=bool(warning),
        )

    def generate_flashcards_from_material(self, user_id: int, material_id: int) -> dict[str, Any]:
        self._assert_user(user_id)
        ai_configured = self._ai_configured()
        if not ai_configured and not self.mock_mode:
            raise AIServiceError("A IA ainda não foi configurada no servidor.")
        context = self.context_service.build_student_context(user_id)
        material = self._require_material(user_id, material_id)
        prompt_text = self.material_service.content_for_prompt(material, 9500)
        response = self.gateway.generate_json(
            "flashcards",
            "generate_flashcards_from_material",
            build_system_prompt("flashcards")
            + "\nResponda no formato: {\"flashcards\": [{\"front\":..., \"back\":..., \"subject\":..., \"difficulty\":...}]}",
            (
                f"Material selecionado: {self.material_service.material_source(material)}\n"
                f"Conteúdo:\n{prompt_text}\n"
                "Gerar no máximo 15 flashcards objetivos."
            ),
            max_tokens=1400,
        )
        if not response.used_ai:
            if self.mock_mode:
                suggestions = self.flashcard_service.sanitize_suggestions(
                    [
                        {
                            "front": f"Qual é o conceito central de {material.title}?",
                            "back": "Resumo do conceito principal em uma frase curta.",
                            "subject": material.subject or "geral",
                            "difficulty": "medio",
                        }
                    ],
                    material,
                )
                warning = "Modo simulado: a IA real ainda não está conectada."
                used_ai = False
            elif response.error_code == "AI_PROVIDER_NOT_CONFIGURED":
                raise AIServiceError(
                    response.friendly_message or "A IA ainda não foi configurada no servidor.",
                    code=response.error_code or "AI_PROVIDER_NOT_CONFIGURED",
                )
            else:
                suggestions = self.flashcard_service.sanitize_suggestions(
                    [
                        {
                            "front": f"O que é essencial lembrar sobre {material.title}?",
                            "back": truncate_text(prompt_text, 160),
                            "subject": material.subject or "geral",
                            "difficulty": "medio",
                        }
                    ],
                    material,
                )
                warning = response.friendly_message or "A IA real está indisponível no momento."
                used_ai = False
        else:
            payload = response.data
            cards_raw = payload.get("flashcards") if isinstance(payload, dict) else payload
            suggestions = self.flashcard_service.sanitize_suggestions(as_list(cards_raw), material)
            warning = None
            used_ai = True

        return self._response(
            answer="Sugestões de flashcards prontas. Revise e aplique quando desejar.",
            mode="flashcards",
            context=context,
            sources=[{"type": "material", "title": material.title, "id": material.id}],
            actions=[
                {
                    "label": "Aplicar sugestão",
                    "action": "create_flashcards",
                    "payload": {"material_id": material.id, "cards": suggestions},
                }
            ],
            used_ai=used_ai,
            warning=warning,
            mock_mode=bool(warning),
            extra={"suggested_flashcards": suggestions},
        )

    def generate_pending_tasks_from_material(self, user_id: int, material_id: int) -> dict[str, Any]:
        self._assert_user(user_id)
        ai_configured = self._ai_configured()
        if not ai_configured and not self.mock_mode:
            raise AIServiceError("A IA ainda não foi configurada no servidor.")
        context = self.context_service.build_student_context(user_id)
        material = self._require_material(user_id, material_id)
        prompt_text = self.material_service.content_for_prompt(material, 9000)
        response = self.gateway.generate_json(
            "materials",
            "generate_tasks_from_material",
            build_system_prompt("organizador")
            + "\nResponda no formato: {\"tasks\": [{\"title\":..., \"description\":..., \"priority\":..., \"source_type\":..., \"estimated_minutes\":..., \"due_in_days\":...}]}",
            (
                f"Material selecionado: {self.material_service.material_source(material)}\n"
                f"Conteúdo:\n{prompt_text}\n"
                "Gerar até 8 pendências objetivas e realistas."
            ),
            max_tokens=1400,
        )
        if not response.used_ai:
            if self.mock_mode:
                suggestions = self.material_service.sanitize_task_suggestions(
                    [
                        {
                            "title": f"Revisar pontos-chave de {material.title}",
                            "description": "Leia os tópicos centrais e produza 5 perguntas de recuperação ativa.",
                            "priority": "média",
                            "source_type": material.source_type or "personal",
                            "estimated_minutes": 45,
                            "due_in_days": 2,
                        }
                    ],
                    material,
                )
                warning = "Modo simulado: a IA real ainda não está conectada."
                used_ai = False
            elif response.error_code == "AI_PROVIDER_NOT_CONFIGURED":
                raise AIServiceError(
                    response.friendly_message or "A IA ainda não foi configurada no servidor.",
                    code=response.error_code or "AI_PROVIDER_NOT_CONFIGURED",
                )
            else:
                suggestions = self.material_service.sanitize_task_suggestions(
                    [
                        {
                            "title": f"Estudar {material.title} em bloco curto",
                            "description": "Converter o material em 3 objetivos de estudo e resolver questões rápidas.",
                            "priority": "média",
                            "source_type": material.source_type or "personal",
                            "estimated_minutes": 40,
                            "due_in_days": 1,
                        }
                    ],
                    material,
                )
                warning = response.friendly_message or "A IA real está indisponível no momento."
                used_ai = False
        else:
            payload = response.data
            tasks_raw = payload.get("tasks") if isinstance(payload, dict) else payload
            suggestions = self.material_service.sanitize_task_suggestions(as_list(tasks_raw), material)
            warning = None
            used_ai = True

        return self._response(
            answer="Sugestões de pendências prontas. Revise e aplique quando desejar.",
            mode="organizador",
            context=context,
            sources=[{"type": "material", "title": material.title, "id": material.id}],
            actions=[
                {
                    "label": "Aplicar sugestão",
                    "action": "create_tasks",
                    "payload": {"material_id": material.id, "tasks": suggestions},
                }
            ],
            used_ai=used_ai,
            warning=warning,
            mock_mode=bool(warning),
            extra={"suggested_tasks": suggestions},
        )

    def generate_weekly_report_insights(self, user_id: int) -> dict[str, Any]:
        self._assert_user(user_id)
        ai_configured = self._ai_configured()
        if not ai_configured and not self.mock_mode:
            raise AIServiceError("A IA ainda não foi configurada no servidor.")
        context = self.context_service.build_student_context(user_id)
        weekly_report = context.get("weekly_report") or {}
        response = self.report_service.generate_weekly_insights(
            weekly_report=weekly_report,
            context_counts=self.context_service.used_context_summary(context),
        )
        if not response.used_ai:
            if not self.mock_mode:
                if response.error_code == "AI_PROVIDER_NOT_CONFIGURED":
                    raise AIServiceError(
                        response.friendly_message or "A IA ainda não foi configurada no servidor.",
                        code=response.error_code or "AI_PROVIDER_NOT_CONFIGURED",
                    )
                answer = (
                    "IA indisponível no momento. Insight local da semana:\n"
                    f"- Tarefas concluídas: {weekly_report.get('completed_tasks', 0)}\n"
                    f"- Carga planejada: {weekly_report.get('planned_minutes', 0)} min\n"
                    f"- Carga concluída: {weekly_report.get('completed_minutes', 0)} min\n"
                    "- Próxima ação: priorize pendências com prazo mais curto e mantenha revisão ativa."
                )
                warning = response.friendly_message or "A IA real está indisponível no momento."
                used_ai = False
                return self._response(
                    answer=answer,
                    mode="analista",
                    context=context,
                    sources=self._sources_for_context(context, None),
                    actions=[],
                    used_ai=used_ai,
                    warning=warning,
                    mock_mode=False,
                    extra={"weekly_report": weekly_report},
                )
            answer = (
                "Modo simulado: visão semanal preliminar.\n"
                f"- Tarefas concluídas: {weekly_report.get('completed_tasks', 0)}\n"
                f"- Carga planejada: {weekly_report.get('planned_minutes', 0)} min\n"
                "A IA real não está conectada para gerar insights avançados."
            )
            warning = "Modo simulado: a IA real ainda não está conectada."
            used_ai = False
        else:
            answer = response.text
            warning = None
            used_ai = True
        return self._response(
            answer=answer,
            mode="analista",
            context=context,
            sources=self._sources_for_context(context, None),
            actions=[],
            used_ai=used_ai,
            warning=warning,
            mock_mode=bool(warning),
            extra={"weekly_report": weekly_report},
        )

    def apply_action(self, user_id: int, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._assert_user(user_id)
        action_key = (action or "").strip().lower()
        if action_key == "create_flashcards":
            material = self.context_service.material_for_user(user_id, int(payload.get("material_id") or 0))
            cards = self.flashcard_service.sanitize_suggestions(payload.get("cards") or [], material)
            created = self.flashcard_service.apply_suggestions(material, cards)
            return {
                "message": f"{len(created)} flashcards criados.",
                "created_flashcards": [self._flashcard_dict(item) for item in created],
            }
        if action_key == "create_tasks":
            material = self.context_service.material_for_user(user_id, int(payload.get("material_id") or 0))
            tasks = self.material_service.sanitize_task_suggestions(payload.get("tasks") or [], material)
            created = self.material_service.apply_task_suggestions(material, tasks)
            return {
                "message": f"{len(created)} pendências criadas.",
                "created_tasks": [self._task_dict(item) for item in created],
            }
        if action_key == "apply_reorganize_week":
            preview = payload.get("preview")
            if not isinstance(preview, list):
                raise AIServiceError("Preview inválido para aplicar reorganização.", code="VALIDATION_ERROR")
            result = self.planner_service.apply_reorganize_week(preview)
            return {
                "message": result.get("message") or "Reorganização aplicada.",
                "rescheduled": result.get("rescheduled", 0),
            }
        raise AIServiceError("Ação não suportada.", code="VALIDATION_ERROR")

    def _chat_prompt(self, message: str, context: dict[str, Any], material: Material | None) -> str:
        material_payload = self.material_service.material_source(material) if material else None
        return (
            f"Mensagem do estudante:\n{message}\n\n"
            f"Contexto do estudante:\n{json.dumps(context, ensure_ascii=False, default=str)[:12000]}\n\n"
            f"Material selecionado:\n{json.dumps(material_payload, ensure_ascii=False, default=str) if material_payload else 'nenhum'}"
        )

    def _missing_data_for_mode(
        self,
        mode: str,
        context: dict[str, Any],
        material: Material | None,
    ) -> list[str]:
        counts = context.get("counts") or {}
        missing: list[str] = []
        if mode in {"organizador", "priorizador"}:
            if int(counts.get("tasks") or 0) == 0:
                missing.append("pendências")
            if int(counts.get("events") or 0) == 0 and not context.get("routine", {}).get("weekly_blocks"):
                missing.append("rotina/calendário")
        if mode == "analista":
            if int(counts.get("simulados") or 0) == 0:
                missing.append("simulados")
            if int(counts.get("redacoes") or 0) == 0:
                missing.append("redações")
        if mode in {"tutor_fontes", "flashcards"}:
            if not material and int(counts.get("materials") or 0) == 0:
                missing.append("materiais")
        if mode == "recuperacao":
            overdue = int(counts.get("overdue_tasks") or 0)
            if overdue == 0 and int(counts.get("tasks") or 0) == 0:
                missing.append("pendências")
        return sorted(set(missing))

    def _sources_for_context(self, context: dict[str, Any], material: Material | None) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        if material:
            sources.append({"type": "material", "title": material.title, "id": material.id})
        for task in (context.get("today_tasks") or [])[:3]:
            sources.append({"type": "task", "title": task.get("title"), "id": task.get("id")})
        for exam in (context.get("exam_history") or [])[:2]:
            sources.append(
                {
                    "type": "simulado",
                    "title": f"{exam.get('type') or 'Simulado'} ({exam.get('date') or 'sem data'})",
                    "id": exam.get("id"),
                }
            )
        for essay in (context.get("essay_history") or [])[:2]:
            sources.append(
                {
                    "type": "redacao",
                    "title": f"{essay.get('theme') or 'Redação'} ({essay.get('date') or 'sem data'})",
                    "id": essay.get("id"),
                }
            )
        if context.get("weekly_report"):
            sources.append({"type": "report", "title": "Relatório semanal interno", "id": 0})
        return sources[:10]

    def _default_actions(self, mode: str, material_id: int | None, context: dict[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        if material_id:
            actions.append(
                {
                    "label": "Gerar flashcards",
                    "action": "prepare_flashcards_from_material",
                    "payload": {"material_id": material_id},
                }
            )
            actions.append(
                {
                    "label": "Gerar pendências",
                    "action": "prepare_tasks_from_material",
                    "payload": {"material_id": material_id},
                }
            )
        if mode == "recuperacao":
            actions.append({"label": "Reorganizar semana", "action": "run_reorganize_week", "payload": {}})
        if mode == "priorizador":
            actions.append({"label": "Ver prioridades", "action": "run_prioritize_tasks", "payload": {}})
        if mode == "analista":
            actions.append({"label": "Gerar insight semanal", "action": "run_weekly_insights", "payload": {}})
        if not actions and int((context.get("counts") or {}).get("materials") or 0):
            first_material = (context.get("recent_materials") or [{}])[0]
            material_id_value = first_material.get("id")
            if material_id_value:
                actions.append(
                    {
                        "label": "Gerar flashcards",
                        "action": "prepare_flashcards_from_material",
                        "payload": {"material_id": material_id_value},
                    }
                )
        return actions

    def _mock_chat_response(
        self,
        mode: str,
        context: dict[str, Any],
        message: str,
        material: Material | None,
    ) -> str:
        counts = context.get("counts") or {}
        base = (
            "Modo simulado: a IA real não está conectada. "
            "Use esta resposta apenas como rascunho."
        )
        if mode == "organizador":
            return (
                f"{base}\n\n"
                f"Você tem {counts.get('today_tasks', 0)} tarefas para hoje e {counts.get('overdue_tasks', 0)} atrasadas. "
                "Comece por uma pendência crítica de 50 min, depois revisão ativa de 25 min."
            )
        if mode == "analista":
            return (
                f"{base}\n\n"
                f"Dados atuais: {counts.get('simulados', 0)} simulados e {counts.get('redacoes', 0)} redações registradas. "
                "Priorize análise de erros e revisão dos tópicos com mais atraso."
            )
        if mode == "tutor_fontes":
            return (
                f"{base}\n\n"
                f"Pergunta recebida: {truncate_text(message, 240)}. "
                f"Material selecionado: {material.title if material else 'nenhum'}."
            )
        if mode == "flashcards":
            return f"{base}\n\nPosso montar flashcards quando você confirmar o material."
        if mode == "recuperacao":
            return (
                f"{base}\n\n"
                "Plano rascunho: reduzir sobrecarga, reagendar atrasadas em blocos curtos e preservar descanso."
            )
        return f"{base}\n\nPosso priorizar suas pendências com base em prazo e impacto."

    def _response(
        self,
        *,
        answer: str,
        mode: str,
        context: dict[str, Any],
        sources: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        used_ai: bool,
        warning: str | None = None,
        mock_mode: bool = False,
        provider: str | None = None,
        model: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "answer": answer,
            "mode": mode,
            "used_context": self.context_service.used_context_summary(context),
            "sources": sources,
            "actions": actions,
            "used_ai": used_ai,
            "warning": warning,
            "mock_mode": mock_mode,
            "provider": provider,
            "model": model,
        }
        if extra:
            payload.update(extra)
        return payload

    def _require_material(self, user_id: int, material_id: int) -> Material:
        material = self.context_service.material_for_user(user_id, material_id)
        if not material:
            raise AIServiceError("Material não encontrado para este usuário.", code="NOT_FOUND")
        return material

    def _assert_user(self, user_id: int) -> None:
        if user_id != self.user_id:
            raise AIServiceError("Usuário inválido para a sessão atual.", code="FORBIDDEN")

    def _ai_configured(self) -> bool:
        try:
            candidates = self.gateway._resolve_candidates("general")
            return bool(candidates)
        except Exception:
            return False

    def _task_dict(self, task: StudyTask) -> dict[str, Any]:
        due = task.due_date or task.deadline
        return {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "priority": task.priority,
            "status": task.status,
            "source_type": task.source_type,
            "subject": task.subject,
            "deadline": due.isoformat() if due else None,
            "estimated_minutes": task.estimated_minutes,
        }

    def _flashcard_dict(self, card: Flashcard) -> dict[str, Any]:
        return {
            "id": card.id,
            "front": card.front,
            "back": card.back,
            "difficulty": card.difficulty,
            "subject": card.subject,
            "topic": card.topic,
        }


def build_user_context(user_id: int, db: Session | None = None) -> dict[str, Any]:
    if db is None:
        raise RuntimeError("build_user_context agora requer sessão ativa do banco.")
    return AIContextService(db).build_student_context(user_id)


def generate_response(
    user_id: int,
    mode: str,
    message: str,
    context: dict[str, Any] | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    if db is None:
        raise RuntimeError("generate_response agora requer sessão ativa do banco.")
    service = AIService(db, user_id)
    payload = service.chat(user_id, message, mode)
    return {"text": payload["answer"], "used_ai": bool(payload.get("used_ai")), "provider": payload.get("provider")}
