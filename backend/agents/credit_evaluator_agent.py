"""Agent 2: Credit Evaluator — queries ML model and translates result for the user.

Presents approved users with up to 3 loan term options in a comparison table.
Rejected users get an empathetic "aún no" response with automatic handoff to
the Financial Advisor agent along with improvement factor context.
"""

import json

from backend.agents.base_agent import BaseAgent, AgentResponse, Tool
from backend.llm.provider import LLMProvider

# -----------------------------------------------------------------------
# Colombian microcrédito rate constants
# -----------------------------------------------------------------------
# Superintendencia Financiera de Colombia caps microcrédito annual rates.
# Real-world effective annual rates sit around 28-42% for microcrédito,
# which translates to ~2.1-2.9% monthly effective.

MONTHLY_RATE_DEFAULT = 0.025  # 2.5% monthly (≈34.5% effective annual)

# Term options offered to approved users
_TERM_OPTIONS = [6, 12, 18]  # months

from backend.agents.prompt_loader import load_prompt

_SYSTEM_PROMPT = load_prompt("credit_evaluator")

# -----------------------------------------------------------------------
# Tools
# -----------------------------------------------------------------------

_TOOLS = [
    Tool(
        name="get_credit_prediction",
        description="Consulta el modelo ML de scoring crediticio para evaluar elegibilidad.",
        parameters={
            "type": "object",
            "properties": {
                "declared_income": {"type": "number", "description": "Ingreso mensual en COP"},
                "employment_type": {
                    "type": "string",
                    "enum": ["informal", "formal", "independent"],
                },
                "is_banked": {"type": "boolean"},
                "age": {"type": "integer"},
                "city_type": {"type": "string", "enum": ["urban", "rural"]},
                "education_level": {
                    "type": "string",
                    "enum": ["none", "primary", "secondary", "technical", "university"],
                },
            },
            "required": ["declared_income"],
        },
    ),
    Tool(
        name="get_loan_simulation",
        description="Simula un préstamo: calcula cuota mensual, costo total e intereses.",
        parameters={
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Monto del préstamo en COP",
                },
                "term_months": {
                    "type": "integer",
                    "description": "Plazo en meses",
                },
                "monthly_rate": {
                    "type": "number",
                    "description": "Tasa mensual (default 0.025 = 2.5%)",
                },
            },
            "required": ["amount", "term_months"],
        },
    ),
]


# -----------------------------------------------------------------------
# Loan simulation math
# -----------------------------------------------------------------------

def simulate_loan(
    amount: float,
    term_months: int,
    monthly_rate: float = MONTHLY_RATE_DEFAULT,
) -> dict:
    """Calculate loan amortisation using standard annuity formula.

    Monthly payment = P * r * (1+r)^n / ((1+r)^n - 1)

    Returns dict with monthly_payment, total_cost, total_interest,
    effective_annual_rate, and monthly_rate.
    """
    if amount <= 0 or term_months <= 0:
        return {
            "monthly_payment": 0,
            "total_cost": 0,
            "total_interest": 0,
            "effective_annual_rate": 0,
            "monthly_rate": monthly_rate,
        }

    r = monthly_rate
    n = term_months
    # Standard annuity formula
    factor = (1 + r) ** n
    monthly_payment = amount * r * factor / (factor - 1)
    total_cost = monthly_payment * n
    total_interest = total_cost - amount
    # Effective annual rate: (1 + r_monthly)^12 - 1
    effective_annual_rate = (1 + r) ** 12 - 1

    return {
        "monthly_payment": round(monthly_payment),
        "total_cost": round(total_cost),
        "total_interest": round(total_interest),
        "effective_annual_rate": round(effective_annual_rate, 4),
        "monthly_rate": r,
    }


def build_options_table(max_amount: float, monthly_rate: float = MONTHLY_RATE_DEFAULT) -> list[dict]:
    """Build up to 3 term options with loan simulation for the max approved amount."""
    options = []
    for term in _TERM_OPTIONS:
        sim = simulate_loan(max_amount, term, monthly_rate)
        options.append({
            "term_months": term,
            "amount": max_amount,
            **sim,
        })
    return options


# -----------------------------------------------------------------------
# CreditEvaluatorAgent
# -----------------------------------------------------------------------

class CreditEvaluatorAgent(BaseAgent):
    """Queries the ML scoring service and presents the result."""

    name = "credit_evaluator"
    system_prompt = _SYSTEM_PROMPT
    tools = _TOOLS
    _tool_handlers = {}

    def __init__(self, llm: LLMProvider, ml_client=None):
        super().__init__(llm)
        self._ml_client = ml_client
        self._tool_handlers = {
            "get_credit_prediction": self._handle_get_prediction,
            "get_loan_simulation": self._handle_get_simulation,
        }

    # ------------------------------------------------------------------
    # Main process — state-driven
    # ------------------------------------------------------------------

    async def process(self, message: str, context: dict, *, original_message: str | None = None) -> AgentResponse:
        # If we already have a prediction in context, use it directly
        prediction = context.get("prediction_result")

        if prediction is None:
            # Call ML service
            prediction = await self._get_prediction(context)
            context["prediction_result"] = prediction

        if prediction.get("eligible"):
            return await self._handle_approved(message, context, prediction)
        else:
            return await self._handle_rejected(message, context, prediction)

    async def process_stream(self, message: str, context: dict, *, original_message: str | None = None):
        response = await self.process(message, context, original_message=original_message)
        yield response.content

    # ------------------------------------------------------------------
    # Approved path
    # ------------------------------------------------------------------

    async def _handle_approved(self, message: str, context: dict, prediction: dict) -> AgentResponse:
        max_amount = prediction.get("max_amount", 500_000)
        product = prediction.get("recommended_product", "nano")
        options = build_options_table(max_amount)

        # Build a text table for the LLM to wrap conversationally
        table_lines = [
            f"| {o['term_months']} meses | ${o['amount']:,.0f} "
            f"| ${o['monthly_payment']:,.0f}/mes "
            f"| ${o['total_interest']:,.0f} intereses "
            f"| TEA {o['effective_annual_rate']:.1%} |"
            for o in options
        ]
        table_text = "\n".join(table_lines)

        instruction = (
            f"[ESTADO: APROBADO. Producto: {product}crédito. "
            f"Monto máximo: ${max_amount:,.0f} COP.\n"
            f"Opciones de plazo:\n{table_text}\n"
            f"Presenta estas opciones de forma clara y amigable. "
            f"Felicita al usuario. NUNCA menciones el score numérico.]"
        )

        content = await self._llm_respond(message, context, instruction)

        return AgentResponse(
            content=content,
            agent_name=self.name,
            agent_type="evaluator",
            suggested_actions=[
                f"Simular a {t} meses" for t in _TERM_OPTIONS
            ] + ["Solicitar crédito"],
            metadata={
                "eligible": True,
                "max_amount": max_amount,
                "product": product,
                "options": options,
                "contract_template": {
                    "max_amount": max_amount,
                    "options": options,
                    "monthly_rate": MONTHLY_RATE_DEFAULT,
                    "conditions": [
                        "Tasa efectiva anual: ~34.5%",
                        "Sin codeudor requerido para montos hasta $500.000",
                        "Desembolso en 24 horas hábiles",
                        "Pago mensual por débito automático o en sucursal",
                        "Seguro de vida incluido sin costo adicional",
                    ],
                },
            },
        )

    # ------------------------------------------------------------------
    # Rejected path
    # ------------------------------------------------------------------

    async def _handle_rejected(self, message: str, context: dict, prediction: dict) -> AgentResponse:
        factors = prediction.get("factors", [])
        # Pick top 3 negative factors
        negative_factors = [f for f in factors if f.get("impact") == "negative"][:3]
        factor_names = [f.get("name", "") for f in negative_factors]

        # Translate factor names to user-friendly Spanish
        factor_descriptions = [_humanize_factor(f) for f in negative_factors]

        instruction = (
            "[ESTADO: AÚN NO califica. "
            "Factores principales a mejorar:\n"
            + "\n".join(f"- {d}" for d in factor_descriptions)
            + "\n"
            "IMPORTANTE: NUNCA uses la palabra 'rechazado'. Di 'aún no estás listo' "
            "o 'todavía no calificas'. Sé empático y motivador. "
            "Explica que lo vamos a ayudar a mejorar con un plan personalizado. "
            "NUNCA menciones scores ni variables del modelo.]"
        )

        content = await self._llm_respond(message, context, instruction)

        return AgentResponse(
            content=content,
            agent_name=self.name,
            agent_type="evaluator",
            handoff_to="financial_advisor",
            suggested_actions=["Ver plan de mejora", "Hablar con asesor financiero"],
            metadata={
                "eligible": False,
                "rejection_factors": factor_names,
                "factors_detail": negative_factors,
                "improvement_factors": [
                    {
                        "factor_name": f.get("name", ""),
                        "current_value": 0,
                        "target_value": 1.0,
                        "potential_reduction": 0.05,
                    }
                    for f in negative_factors
                ],
            },
        )

    # ------------------------------------------------------------------
    # ML service integration
    # ------------------------------------------------------------------

    async def _get_prediction(self, context: dict) -> dict:
        """Get credit prediction from ML service or mock."""
        if self._ml_client:
            from backend.ml_client.schemas import RiskRequest
            user_data = context.get("user_data", {})
            request = RiskRequest(
                declared_income=user_data.get("income", 1_000_000),
                is_banked=1 if user_data.get("is_banked", True) else 0,
                employment_type=user_data.get("employment_type", "informal"),
                age=user_data.get("age", 30),
                city_type=user_data.get("city_type", "urban"),
                total_sessions=user_data.get("total_sessions", 0),
                pct_conversion=user_data.get("pct_conversion", 0.0),
                tx_income_pct=user_data.get("tx_income_pct", 0.0),
                payments_count=user_data.get("payments_count", 0),
                on_time_rate=user_data.get("on_time_rate", 0.5),
                overdue_rate=user_data.get("overdue_rate", 0.0),
                avg_decision_score=user_data.get("avg_decision_score", 0.5),
            )
            pred = await self._ml_client.predict(request)
            return {
                "eligible": pred.eligible,
                "p_default": pred.p_default,
                "max_amount": pred.max_amount,
                "recommended_product": pred.recommended_product.value if pred.recommended_product else None,
                "score_band": pred.score_band.value,
                "factors": [{"name": f.name, "impact": f.impact, "weight": f.weight} for f in pred.factors],
                "risk_category": pred.risk_category,
                "decision": pred.decision,
            }

        # Mock fallback
        user_data = context.get("user_data", {})
        income = user_data.get("income", 1_000_000)
        eligible = context.get("prediction_eligible", income >= 1_200_000)
        return {
            "eligible": eligible,
            "p_default": 0.15 if eligible else 0.65,
            "max_amount": min(income * 2, 2_000_000) if eligible else None,
            "recommended_product": "micro" if eligible and income > 1_500_000 else "nano" if eligible else None,
            "score_band": "low_risk" if eligible else "high_risk",
            "factors": [
                {"name": "declared_income", "impact": "positive" if income > 1_000_000 else "negative", "weight": 0.2},
                {"name": "is_banked", "impact": "negative", "weight": 0.2},
                {"name": "on_time_rate", "impact": "negative", "weight": 0.6},
            ],
            "risk_category": "low" if eligible else "high",
            "decision": "approved" if eligible else "rejected",
        }

    # ------------------------------------------------------------------
    # Tool handlers (for LLM-driven tool loop via BaseAgent._run_with_tools)
    # ------------------------------------------------------------------

    async def _handle_get_prediction(self, context: dict, **kwargs) -> str:
        # Merge kwargs into user_data for the prediction call
        user_data = context.get("user_data", {})
        user_data.update(kwargs)
        context["user_data"] = user_data
        result = await self._get_prediction(context)
        context["prediction_result"] = result
        return json.dumps(result)

    async def _handle_get_simulation(self, context: dict, **kwargs) -> str:
        amount = kwargs.get("amount", 500_000)
        term_months = kwargs.get("term_months", 12)
        monthly_rate = kwargs.get("monthly_rate", MONTHLY_RATE_DEFAULT)
        result = simulate_loan(amount, term_months, monthly_rate)
        return json.dumps(result)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _llm_respond(self, message: str, context: dict, state_instruction: str) -> str:
        """Call LLM with system prompt + history + state instruction."""
        # Merge state instruction into the system prompt so it appears once at the top.
        # Inserting a system message mid-conversation confuses smaller models (empty output).
        combined_system = self.system_prompt or ""
        if state_instruction:
            combined_system = (combined_system + "\n\n" + state_instruction).strip()

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
        return "evaluator"


# -----------------------------------------------------------------------
# Factor humanization
# -----------------------------------------------------------------------

_FACTOR_TRANSLATIONS = {
    "declared_income": "Tus ingresos mensuales declarados",
    "is_banked": "No contar con productos bancarios activos",
    "on_time_rate": "Tu historial de pagos puntuales",
    "overdue_rate": "Tienes pagos atrasados en tu historial",
    "rejection_rate": "Has tenido solicitudes de crédito rechazadas previamente",
    "pct_conversion": "Tu actividad digital con el banco es baja",
    "base_risk_score": "Tu perfil demográfico general",
    "employment_type": "Tu tipo de empleo actual",
    "age": "Tu edad",
    "education_level": "Tu nivel educativo",
    "household_size": "El tamaño de tu hogar",
}


def _humanize_factor(factor: dict) -> str:
    """Translate a risk factor dict into a user-friendly Spanish description."""
    name = factor.get("name", "")
    return _FACTOR_TRANSLATIONS.get(name, f"Factor: {name}")
