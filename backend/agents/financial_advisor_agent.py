"""Agent 4: Financial Advisor — personalized coaching with gamification.

Creates multi-week improvement plans built from ML factor analysis, presented
as missions with points, levels, and progress tracking. Missions are
personalised to the user's occupation (e.g. arepas vendor, domestic worker).

Gamification hierarchy:
    Mission → Plan (4-8 weeks) → Level (accumulated points)
"""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timedelta
from typing import Any

from backend.agents.base_agent import BaseAgent, AgentResponse, Tool
from backend.llm.provider import LLMProvider

# -----------------------------------------------------------------------
# System prompt
# -----------------------------------------------------------------------

from backend.agents.prompt_loader import load_prompt

_SYSTEM_PROMPT = load_prompt("financial_advisor")

# -----------------------------------------------------------------------
# Points & levels
# -----------------------------------------------------------------------

LEVEL_THRESHOLDS = [
    (0, "Principiante"),
    (50, "Aprendiz"),
    (150, "Disciplinado"),
    (300, "Experto"),
    (500, "Maestro Financiero"),
]


def compute_level(total_points: int) -> dict:
    """Return current level info based on accumulated points."""
    level_name = LEVEL_THRESHOLDS[0][1]
    level_index = 0
    next_threshold: int | None = LEVEL_THRESHOLDS[1][0] if len(LEVEL_THRESHOLDS) > 1 else None

    for i, (threshold, name) in enumerate(LEVEL_THRESHOLDS):
        if total_points >= threshold:
            level_name = name
            level_index = i
            next_threshold = (
                LEVEL_THRESHOLDS[i + 1][0] if i + 1 < len(LEVEL_THRESHOLDS) else None
            )

    return {
        "level": level_index + 1,
        "level_name": level_name,
        "total_points": total_points,
        "next_level_at": next_threshold,
        "points_to_next": (next_threshold - total_points) if next_threshold else 0,
    }


# -----------------------------------------------------------------------
# Mission catalog — linked to ML factors
# -----------------------------------------------------------------------

# Each template: (id_prefix, factor_name, points, title, description_template,
#                  completion_criteria, weeks_to_complete)
# {occupation} is replaced at plan-build time with the user's actual occupation.

MISSION_CATALOG: list[dict] = [
    # --- on_time_rate missions (most impactful factor, weight 2.6) ---
    {
        "id_prefix": "deposit_constant",
        "factor": "on_time_rate",
        "points": 15,
        "title": "Depósito Constante",
        "description": "Deposita en tu cuenta al menos {deposit_count} veces esta semana. "
                       "{occupation_tip}",
        "criteria": "deposit_count >= {deposit_count} en 7 días",
        "weeks": 1,
        "difficulty": "easy",
        "deposit_count": 3,
    },
    {
        "id_prefix": "salary_registered",
        "factor": "on_time_rate",
        "points": 25,
        "title": "Ingreso Registrado",
        "description": "Recibe tu pago o ingreso principal directamente en tu cuenta BBVA. "
                       "{occupation_tip}",
        "criteria": "ingreso >= 80% del ingreso declarado recibido en cuenta",
        "weeks": 2,
        "difficulty": "medium",
    },
    {
        "id_prefix": "on_time_payment",
        "factor": "on_time_rate",
        "points": 30,
        "title": "Pago Puntual",
        "description": "Paga todas tus obligaciones antes de la fecha de vencimiento "
                       "durante {weeks} semanas consecutivas.",
        "criteria": "0 pagos vencidos durante el periodo",
        "weeks": 3,
        "difficulty": "medium",
    },
    # --- overdue_rate missions (weight 1.9) ---
    {
        "id_prefix": "zero_overdue",
        "factor": "overdue_rate",
        "points": 35,
        "title": "Cero Atrasos",
        "description": "Mantén cero pagos en mora durante {weeks} semanas. "
                       "Si tienes pagos atrasados, ponte al día primero.",
        "criteria": "overdue_count == 0 durante {weeks} semanas",
        "weeks": 4,
        "difficulty": "hard",
    },
    # --- pct_conversion / digital engagement missions (weight 1.0) ---
    {
        "id_prefix": "digital_explorer",
        "factor": "pct_conversion",
        "points": 10,
        "title": "Explorador Digital",
        "description": "Usa la app BBVA al menos 3 veces esta semana: consulta tu saldo, "
                       "haz una transferencia, paga un servicio.",
        "criteria": "sessions >= 3 en 7 días con al menos 1 transacción",
        "weeks": 1,
        "difficulty": "easy",
    },
    {
        "id_prefix": "payment_digital",
        "factor": "pct_conversion",
        "points": 15,
        "title": "Pago Digital",
        "description": "Haz al menos 2 pagos de servicios (agua, luz, gas, celular) "
                       "a través de la app BBVA.",
        "criteria": "bill_payments >= 2 en 14 días via app",
        "weeks": 2,
        "difficulty": "easy",
    },
    # --- is_banked / balance missions (weight 0.2 but visible to user) ---
    {
        "id_prefix": "safety_cushion",
        "factor": "is_banked",
        "points": 25,
        "title": "Colchón de Seguridad",
        "description": "Mantén un saldo mayor a $200.000 en tu cuenta durante {weeks} semanas.",
        "criteria": "saldo_minimo_diario >= 200000 durante {weeks} semanas",
        "weeks": 2,
        "difficulty": "medium",
    },
    {
        "id_prefix": "savings_habit",
        "factor": "is_banked",
        "points": 40,
        "title": "Hábito de Ahorro",
        "description": "Separa al menos el 10% de cada ingreso en tu cuenta de ahorro "
                       "durante {weeks} semanas.",
        "criteria": "ahorro >= 10% de ingresos durante {weeks} semanas",
        "weeks": 4,
        "difficulty": "hard",
    },
]

# Occupation-specific tips injected into mission descriptions
_OCCUPATION_TIPS: dict[str, dict[str, str]] = {
    "vendedor_ambulante": {
        "deposit_constant": "¿Vendes arepas o empanadas? Deposita las ganancias del fin de semana en tu cuenta.",
        "salary_registered": "Pide a tus clientes frecuentes que te paguen por Nequi o transferencia a tu cuenta BBVA.",
        "default": "Como vendedor, cada venta que depositas en tu cuenta suma puntos a tu perfil.",
    },
    "trabajador_domestico": {
        "deposit_constant": "Pide a tu empleador que te pague directamente a tu cuenta BBVA.",
        "salary_registered": "Si trabajas por días, deposita lo de cada día apenas lo recibas.",
        "default": "Cada ingreso que registras en tu cuenta demuestra estabilidad financiera.",
    },
    "independiente": {
        "deposit_constant": "Separa un porcentaje de cada trabajo terminado y deposítalo el mismo día.",
        "salary_registered": "Factura tus servicios y recibe los pagos en tu cuenta BBVA.",
        "default": "Como independiente, la clave es demostrar ingresos constantes.",
    },
    "default": {
        "deposit_constant": "Deposita tus ingresos de la semana en tu cuenta.",
        "salary_registered": "Recibe tu ingreso principal en tu cuenta BBVA.",
        "default": "Cada transacción en tu cuenta mejora tu perfil crediticio.",
    },
}


def _get_occupation_tip(occupation: str, mission_id_prefix: str) -> str:
    """Get an occupation-specific tip for a mission."""
    tips = _OCCUPATION_TIPS.get(occupation, _OCCUPATION_TIPS["default"])
    return tips.get(mission_id_prefix, tips.get("default", ""))


# -----------------------------------------------------------------------
# Plan builder
# -----------------------------------------------------------------------

def build_plan(
    improvement_factors: list[dict],
    occupation: str = "default",
    plan_weeks: int = 6,
) -> list[dict]:
    """Build a progressive mission plan from ML improvement factors.

    Selects missions that target the user's weakest ML factors, orders them
    by difficulty (easy → hard) across the plan_weeks window, and assigns
    week numbers.

    Args:
        improvement_factors: list of dicts with at least 'factor_name' and
            'potential_reduction' keys (from MLClient.get_improvement_factors).
        occupation: user's occupation for personalised tips.
        plan_weeks: total plan duration in weeks (4-8).

    Returns:
        List of mission dicts with week assignments and personalised descriptions.
    """
    plan_weeks = max(4, min(8, plan_weeks))

    # Collect factor names the user should improve, ordered by impact
    target_factors = {f["factor_name"] for f in improvement_factors}

    # If no specific factors (already good profile), give engagement missions
    if not target_factors:
        target_factors = {"pct_conversion", "is_banked"}

    # Select relevant missions from catalog
    selected: list[dict] = []
    for template in MISSION_CATALOG:
        if template["factor"] in target_factors:
            mission = _instantiate_mission(template, occupation)
            selected.append(mission)

    # Sort by difficulty to create progression: easy → medium → hard
    difficulty_order = {"easy": 0, "medium": 1, "hard": 2}
    selected.sort(key=lambda m: difficulty_order.get(m["difficulty"], 1))

    # Assign weeks progressively, keeping only missions that fit
    plan: list[dict] = []
    current_week = 1
    for mission in selected:
        if current_week > plan_weeks:
            break
        mission["start_week"] = current_week
        mission["end_week"] = min(current_week + mission["weeks"] - 1, plan_weeks)
        plan.append(mission)
        current_week = mission["end_week"] + 1

    return plan


def _instantiate_mission(template: dict, occupation: str) -> dict:
    """Create a concrete mission instance from a catalog template."""
    tip = _get_occupation_tip(occupation, template["id_prefix"])

    description = template["description"].format(
        occupation_tip=tip,
        deposit_count=template.get("deposit_count", 3),
        weeks=template.get("weeks", 2),
    )

    criteria = template["criteria"].format(
        deposit_count=template.get("deposit_count", 3),
        weeks=template.get("weeks", 2),
    )

    return {
        "mission_id": f"{template['id_prefix']}_{uuid.uuid4().hex[:6]}",
        "factor": template["factor"],
        "points": template["points"],
        "title": template["title"],
        "description": description,
        "criteria": criteria,
        "weeks": template["weeks"],
        "difficulty": template["difficulty"],
        "status": "pending",
        "progress": 0.0,
    }


def calculate_plan_points(missions: list[dict]) -> dict:
    """Summarise points for a plan: total possible, earned, and completion %."""
    total_possible = sum(m["points"] for m in missions)
    earned = sum(m["points"] for m in missions if m.get("status") == "completed")
    return {
        "total_possible": total_possible,
        "earned": earned,
        "completion_pct": round(earned / total_possible * 100, 1) if total_possible else 0,
    }


# -----------------------------------------------------------------------
# Tools
# -----------------------------------------------------------------------

_TOOLS = [
    Tool(
        name="get_user_profile",
        description="Obtiene el perfil financiero del usuario: patrón de ingresos, gastos, historial de saldo.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "ID del usuario"},
            },
            "required": ["user_id"],
        },
    ),
    Tool(
        name="get_improvement_factors",
        description="Obtiene los factores del modelo ML que el usuario puede mejorar, ordenados por impacto.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "ID del usuario"},
            },
            "required": ["user_id"],
        },
    ),
    Tool(
        name="create_mission",
        description="Crea una misión de mejora financiera para el usuario.",
        parameters={
            "type": "object",
            "properties": {
                "mission_type": {
                    "type": "string",
                    "description": "Tipo de misión (e.g. deposit_constant, safety_cushion)",
                },
                "user_id": {"type": "string"},
            },
            "required": ["mission_type", "user_id"],
        },
    ),
    Tool(
        name="update_mission_progress",
        description="Actualiza el progreso de una misión existente.",
        parameters={
            "type": "object",
            "properties": {
                "mission_id": {"type": "string"},
                "progress": {
                    "type": "number",
                    "description": "Progreso 0.0-1.0 (1.0 = completada)",
                },
                "completed": {"type": "boolean", "description": "Marcar como completada"},
            },
            "required": ["mission_id"],
        },
    ),
]


# -----------------------------------------------------------------------
# FinancialAdvisorAgent
# -----------------------------------------------------------------------

class FinancialAdvisorAgent(BaseAgent):
    """Helps users improve their financial health through gamified missions."""

    name = "financial_advisor"
    system_prompt = _SYSTEM_PROMPT
    tools = _TOOLS
    _tool_handlers = {}

    def __init__(self, llm: LLMProvider, ml_client=None):
        super().__init__(llm)
        self._ml_client = ml_client
        self._tool_handlers = {
            "get_user_profile": self._handle_get_profile,
            "get_improvement_factors": self._handle_get_factors,
            "create_mission": self._handle_create_mission,
            "update_mission_progress": self._handle_update_progress,
        }

    # ------------------------------------------------------------------
    # Main process
    # ------------------------------------------------------------------

    async def process(self, message: str, context: dict, *, original_message: str | None = None) -> AgentResponse:
        # Detect what the user wants
        intent = _detect_advisor_intent(message)

        if intent == "create_plan":
            return await self._handle_create_plan(message, context)
        elif intent == "check_progress":
            return await self._handle_check_progress(message, context)
        elif intent == "complete_mission":
            return await self._handle_complete_mission(message, context)
        else:
            # General advice — diagnose + suggest
            return await self._handle_general_advice(message, context)

    async def process_stream(self, message: str, context: dict, *, original_message: str | None = None):
        response = await self.process(message, context, original_message=original_message)
        yield response.content

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    async def _handle_create_plan(self, message: str, context: dict) -> AgentResponse:
        factors = self._get_factors_from_context(context)
        occupation = context.get("user_data", {}).get("occupation", "default")

        plan = build_plan(factors, occupation=occupation)
        context["plan"] = plan
        context["total_points"] = context.get("total_points", 0)

        points_info = calculate_plan_points(plan)
        level_info = compute_level(context["total_points"])

        # Build plan summary for LLM
        plan_lines = []
        for m in plan:
            plan_lines.append(
                f"- Semana {m['start_week']}-{m['end_week']}: "
                f"{m['title']} ({m['points']} pts, {m['difficulty']}) — {m['description'][:80]}..."
            )
        plan_text = "\n".join(plan_lines) if plan_lines else "No hay misiones disponibles."

        instruction = (
            f"[ESTADO: Crear plan personalizado.\n"
            f"Ocupación del usuario: {occupation}\n"
            f"Nivel actual: {level_info['level_name']} ({level_info['total_points']} pts)\n"
            f"Puntos posibles en este plan: {points_info['total_possible']}\n"
            f"Plan de misiones:\n{plan_text}\n"
            f"Presenta el plan de forma motivadora. Usa lenguaje de gamificación "
            f"(misiones, retos, niveles). Explica cada misión brevemente. "
            f"Dile al usuario que al completar misiones sube de nivel.]"
        )

        content = await self._llm_respond(message, context, instruction)

        return AgentResponse(
            content=content,
            agent_name=self.name,
            agent_type="advisor",
            suggested_actions=["Ver mis misiones", "Empezar primera misión"],
            metadata={
                "plan": plan,
                "points": points_info,
                "level": level_info,
            },
        )

    async def _handle_check_progress(self, message: str, context: dict) -> AgentResponse:
        plan = context.get("plan", [])
        total_points = context.get("total_points", 0)

        points_info = calculate_plan_points(plan)
        level_info = compute_level(total_points)

        completed = [m for m in plan if m.get("status") == "completed"]
        in_progress = [m for m in plan if m.get("status") == "in_progress"]
        pending = [m for m in plan if m.get("status") == "pending"]

        instruction = (
            f"[ESTADO: Revisar progreso.\n"
            f"Nivel: {level_info['level_name']} ({total_points} pts)\n"
            f"Misiones completadas: {len(completed)}/{len(plan)}\n"
            f"En progreso: {[m['title'] for m in in_progress]}\n"
            f"Pendientes: {[m['title'] for m in pending]}\n"
            f"Puntos ganados: {points_info['earned']}/{points_info['total_possible']}\n"
            f"{'Faltan ' + str(level_info['points_to_next']) + ' pts para el siguiente nivel.' if level_info['points_to_next'] else 'Nivel máximo alcanzado.'}\n"
            f"Celebra lo logrado, motiva a seguir con las pendientes.]"
        )

        content = await self._llm_respond(message, context, instruction)

        return AgentResponse(
            content=content,
            agent_name=self.name,
            agent_type="advisor",
            suggested_actions=self._progress_actions(in_progress, pending),
            metadata={
                "points": points_info,
                "level": level_info,
                "completed_count": len(completed),
                "total_missions": len(plan),
            },
        )

    async def _handle_complete_mission(self, message: str, context: dict) -> AgentResponse:
        plan = context.get("plan", [])

        # Find the first in-progress or pending mission to complete
        target = None
        for m in plan:
            if m.get("status") in ("in_progress", "pending"):
                target = m
                break

        if target is None:
            content = await self._llm_respond(
                message, context,
                "[ESTADO: No hay misiones pendientes. Felicita al usuario, "
                "sugiere crear un nuevo plan con más misiones.]",
            )
            return AgentResponse(
                content=content,
                agent_name=self.name,
                agent_type="advisor",
                suggested_actions=["Crear nuevo plan"],
            )

        # Complete it
        target["status"] = "completed"
        target["progress"] = 1.0
        context["total_points"] = context.get("total_points", 0) + target["points"]

        level_info = compute_level(context["total_points"])
        points_info = calculate_plan_points(plan)

        instruction = (
            f"[ESTADO: Misión completada: '{target['title']}' (+{target['points']} pts).\n"
            f"Total puntos: {context['total_points']}. "
            f"Nivel: {level_info['level_name']}.\n"
            f"Progreso del plan: {points_info['earned']}/{points_info['total_possible']} pts "
            f"({points_info['completion_pct']}%).\n"
            f"Celebra genuinamente este logro. Si subió de nivel, hazlo especial.]"
        )

        content = await self._llm_respond(message, context, instruction)

        return AgentResponse(
            content=content,
            agent_name=self.name,
            agent_type="advisor",
            suggested_actions=["Ver mis misiones", "Siguiente misión"],
            metadata={
                "completed_mission": target["title"],
                "points_earned": target["points"],
                "level": level_info,
                "points": points_info,
            },
        )

    async def _handle_general_advice(self, message: str, context: dict) -> AgentResponse:
        factors = self._get_factors_from_context(context)
        occupation = context.get("user_data", {}).get("occupation", "default")

        if factors:
            factor_lines = "\n".join(
                f"- {f['factor_name']}: actual={f.get('current_value', '?')}, "
                f"meta={f.get('target_value', '?')}, sugerencia={f.get('suggestion', '')}"
                for f in factors[:3]
            )
            instruction = (
                f"[ESTADO: Asesoría general.\n"
                f"Ocupación: {occupation}\n"
                f"Factores a mejorar (top 3):\n{factor_lines}\n"
                f"Da consejos personalizados basados en estos factores. "
                f"Si el usuario no tiene plan, sugiere crear uno.]"
            )
        else:
            instruction = (
                "[ESTADO: Asesoría general. No hay factores de mejora disponibles. "
                "Pregunta al usuario sobre su situación financiera y sugiere "
                "crear un plan personalizado.]"
            )

        content = await self._llm_respond(message, context, instruction)

        actions = ["Crear plan personalizado", "Consultar mi progreso", "Tips de ahorro"]
        return AgentResponse(
            content=content,
            agent_name=self.name,
            agent_type="advisor",
            suggested_actions=actions,
        )

    # ------------------------------------------------------------------
    # Tool handlers
    # ------------------------------------------------------------------

    async def _handle_get_profile(self, context: dict, **kwargs) -> str:
        """Return user financial profile from context or mock."""
        user_data = context.get("user_data", {})
        profile = {
            "income": user_data.get("income", 1_000_000),
            "occupation": user_data.get("occupation", "informal"),
            "is_banked": user_data.get("is_banked", True),
            "balance_avg": user_data.get("balance_avg", 150_000),
            "monthly_deposits": user_data.get("monthly_deposits", 2),
            "monthly_transactions": user_data.get("monthly_transactions", 5),
        }
        return json.dumps(profile)

    async def _handle_get_factors(self, context: dict, **kwargs) -> str:
        """Return improvement factors from ML client or context."""
        factors = self._get_factors_from_context(context)
        return json.dumps(factors)

    async def _handle_create_mission(self, context: dict, **kwargs) -> str:
        """Create a single mission by type."""
        mission_type = kwargs.get("mission_type", "deposit_constant")
        occupation = context.get("user_data", {}).get("occupation", "default")

        template = next(
            (t for t in MISSION_CATALOG if t["id_prefix"] == mission_type),
            MISSION_CATALOG[0],  # fallback to first mission
        )
        mission = _instantiate_mission(template, occupation)

        # Add to plan in context
        plan = context.setdefault("plan", [])
        plan.append(mission)

        return json.dumps(mission)

    async def _handle_update_progress(self, context: dict, **kwargs) -> str:
        """Update a mission's progress or mark it completed."""
        mission_id = kwargs.get("mission_id", "")
        progress = kwargs.get("progress")
        completed = kwargs.get("completed", False)

        plan = context.get("plan", [])
        target = next((m for m in plan if m["mission_id"] == mission_id), None)

        if target is None:
            return json.dumps({"error": "mission_not_found", "mission_id": mission_id})

        if progress is not None:
            target["progress"] = min(1.0, max(0.0, progress))
        if completed or target["progress"] >= 1.0:
            target["status"] = "completed"
            target["progress"] = 1.0
            context["total_points"] = context.get("total_points", 0) + target["points"]

        level_info = compute_level(context.get("total_points", 0))
        return json.dumps({
            "mission_id": mission_id,
            "status": target["status"],
            "progress": target["progress"],
            "points_earned": target["points"] if target["status"] == "completed" else 0,
            "level": level_info,
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_factors_from_context(self, context: dict) -> list[dict]:
        """Get improvement factors from context (set by orchestrator handoff)."""
        # Factors may come from credit evaluator handoff or direct context
        factors = context.get("improvement_factors", [])
        if not factors:
            # Try to derive from rejection factors
            rejection = context.get("rejection_factors", [])
            if rejection:
                factors = [
                    {"factor_name": name, "current_value": 0, "target_value": 1.0,
                     "potential_reduction": 0.05, "suggestion": ""}
                    for name in rejection
                ]
        return factors

    @staticmethod
    def _progress_actions(in_progress: list, pending: list) -> list[str]:
        actions = []
        if in_progress:
            actions.append(f"Completar: {in_progress[0]['title']}")
        if pending:
            actions.append(f"Empezar: {pending[0]['title']}")
        actions.append("Ver plan completo")
        return actions

    async def _llm_respond(self, message: str, context: dict, instruction: str) -> str:
        # Merge instruction into the system prompt so it appears once at the top.
        # Inserting a system message mid-conversation confuses smaller models (empty output).
        combined_system = self.system_prompt or ""
        if instruction:
            combined_system = (combined_system + "\n\n" + instruction).strip()

        messages = []
        if combined_system:
            messages.append({"role": "system", "content": combined_system})

        # Only include user/assistant turns — system turns mid-history confuse the model.
        # The current user message was already appended to history by the orchestrator
        # before process() was called, so we don't add it again.
        history = context.get("history", [])
        for turn in history[-8:]:
            if turn["role"] in ("user", "assistant"):
                messages.append({"role": turn["role"], "content": turn["content"]})

        return await self.llm.generate(messages, temperature=0.7)

    def _agent_type(self) -> str:
        return "advisor"


# -----------------------------------------------------------------------
# Intent detection (lightweight keyword match)
# -----------------------------------------------------------------------

_PLAN_KEYWORDS = {"plan", "crear plan", "misiones", "retos", "empezar", "quiero mejorar",
                  "ayúdame a mejorar", "cómo mejoro"}
_PROGRESS_KEYWORDS = {"progreso", "avance", "cómo voy", "mis misiones", "mis puntos",
                      "mi nivel", "estado"}
_COMPLETE_KEYWORDS = {"completé", "terminé", "logré", "hice", "cumplí", "ya lo hice",
                      "misión completada", "listo"}


def _detect_advisor_intent(message: str) -> str:
    """Detect user intent for advisor routing."""
    lower = message.lower()

    for kw in _COMPLETE_KEYWORDS:
        if kw in lower:
            return "complete_mission"

    for kw in _PROGRESS_KEYWORDS:
        if kw in lower:
            return "check_progress"

    for kw in _PLAN_KEYWORDS:
        if kw in lower:
            return "create_plan"

    return "general_advice"
