"""Agent 1: Onboarding — guides non-clients through bancarization.

Implements a conversational state machine that collects user data naturally,
evaluates credit eligibility via the ML service, and opens an account.

States: GREETING → COLLECTING_DATA → CONFIRMING → EVALUATING →
        ACCOUNT_OPENING → HELPYY_ACTIVATION

The agent extracts data from free-form text (regex-based) and handles
out-of-order inputs (e.g., user provides name and cedula in one message).
"""

import json
import logging
import re
import uuid
from enum import Enum

from backend.agents.base_agent import BaseAgent, AgentResponse, Tool
from backend.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# States
# -----------------------------------------------------------------------

class OnboardingState(str, Enum):
    GREETING = "greeting"
    COLLECTING_DATA = "collecting_data"
    CONFIRMING = "confirming"
    EVALUATING = "evaluating"
    ACCOUNT_OPENING = "account_opening"
    HELPYY_ACTIVATION = "helpyy_activation"
    DONE = "done"


# -----------------------------------------------------------------------
# System prompt
# -----------------------------------------------------------------------

from backend.agents.prompt_loader import load_prompt

_SYSTEM_PROMPT = load_prompt("onboarding")

# -----------------------------------------------------------------------
# Tools
# -----------------------------------------------------------------------

_TOOLS = [
    Tool(
        name="check_credit_score",
        description="Consulta el modelo ML de scoring crediticio para evaluar elegibilidad del usuario.",
        parameters={
            "type": "object",
            "properties": {
                "declared_income": {"type": "number", "description": "Ingreso mensual en COP"},
                "employment_type": {"type": "string", "enum": ["informal", "formal", "independent"]},
                "is_banked": {"type": "boolean"},
                "age": {"type": "integer"},
                "city_type": {"type": "string", "enum": ["urban", "rural"]},
                "education_level": {"type": "string", "enum": ["none", "primary", "secondary", "technical", "university"]},
            },
            "required": ["declared_income"],
        },
    ),
    Tool(
        name="create_account",
        description="Crea una nueva cuenta bancaria para el usuario.",
        parameters={
            "type": "object",
            "properties": {
                "user_name": {"type": "string"},
                "cedula": {"type": "string"},
            },
            "required": ["user_name", "cedula"],
        },
    ),
    Tool(
        name="enable_helpyy_hand",
        description="Activa el asistente Helpyy Hand para el usuario.",
        parameters={
            "type": "object",
            "properties": {
                "account_id": {"type": "string"},
            },
            "required": ["account_id"],
        },
    ),
]


# -----------------------------------------------------------------------
# Data extraction patterns
# -----------------------------------------------------------------------

# Name: after trigger phrases — matches 1-3 words starting with capital or lowercase
_NAME_PATTERN = re.compile(
    r"(?:(?:me llamo|mi nombre es|soy|nombre completo(?:\s+es)?)\s+)"
    r"([A-ZÁÉÍÓÚÑa-záéíóúñ][a-záéíóúñ]+"
    r"(?:\s+[A-ZÁÉÍÓÚÑa-záéíóúñ][a-záéíóúñ]+){0,2})",
    re.IGNORECASE,
)

# Cedula: 8-10 digit number (standalone)
_CEDULA_PATTERN = re.compile(r"(?<!\d)\d{8,10}(?!\d)")

# Income: number followed by optional thousands/millions indicators
_INCOME_PATTERN = re.compile(
    r"(?:ingreso|gano|salario|sueldo|recibo|mensual|ganancia)[^\d]{0,20}?"
    r"([\d.,]+)\s*(?:millones|millon|mill?|pesos|cop)?",
    re.IGNORECASE,
)
# Also catch standalone large numbers (>= 100000) that look like income
_LARGE_NUMBER_PATTERN = re.compile(r"\b(\d{1,3}(?:[.,]\d{3})*(?:\.\d+)?)\b")


def _parse_income(text: str) -> float | None:
    """Extract income from text. Handles: '1.5 millones', '1500000', '800 mil'."""
    # Try contextual pattern first
    m = _INCOME_PATTERN.search(text)
    if m:
        return _normalize_amount(m.group(1), text[m.start():])

    # Check for "N millones" or "N mil" without income keyword
    millions = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:millones|millon)", text, re.IGNORECASE)
    if millions:
        raw = millions.group(1).replace(",", ".")
        return float(raw) * 1_000_000

    thousands = re.search(r"(\d+(?:[.,]\d+)?)\s*mil\b", text, re.IGNORECASE)
    if thousands:
        raw = thousands.group(1).replace(",", ".")
        return float(raw) * 1_000

    # Fallback: look for large standalone numbers
    for m in _LARGE_NUMBER_PATTERN.finditer(text):
        val = m.group(1).replace(".", "").replace(",", "")
        try:
            num = float(val)
            if num >= 100_000:
                return num
        except ValueError:
            continue

    return None


def _normalize_amount(raw: str, context: str) -> float:
    """Normalize a numeric string with optional thousands/millions context.

    Distinguishes decimal points from thousands separators:
    - "1.500.000" → thousands separators → 1500000
    - "1.5" → decimal point → 1.5
    - "1,5" → decimal comma → 1.5
    """
    # Count dots to decide: multiple dots = thousands separators, single dot = decimal
    dot_count = raw.count(".")
    if dot_count > 1:
        # Multiple dots → all are thousands separators (e.g., "1.500.000")
        clean = raw.replace(".", "").replace(",", ".")
    elif dot_count == 1:
        # Single dot: if followed by exactly 3 digits → thousands separator, else decimal
        parts = raw.split(".")
        if len(parts[1]) == 3 and parts[1].isdigit():
            clean = raw.replace(".", "").replace(",", ".")
        else:
            # Decimal point — keep it, normalize commas before it
            clean = raw.replace(",", "")
    else:
        # No dots — commas might be decimal separators
        clean = raw.replace(",", ".")

    try:
        val = float(clean)
    except ValueError:
        return 0.0

    lower = context.lower()
    if "millon" in lower:
        val *= 1_000_000
    elif "mil" in lower and val < 1_000:
        val *= 1_000

    return val


def extract_data_from_message(text: str) -> dict:
    """Extract onboarding data fields from free-form text.

    Returns a dict with any of: name, cedula, income.
    Only includes fields that were actually found.
    """
    extracted: dict = {}

    # Name
    name_match = _NAME_PATTERN.search(text)
    if name_match:
        extracted["name"] = name_match.group(1).strip()

    # Cedula
    cedula_match = _CEDULA_PATTERN.search(text)
    if cedula_match:
        extracted["cedula"] = cedula_match.group(0)

    # Income
    income = _parse_income(text)
    if income is not None and income >= 100_000:
        extracted["income"] = income

    return extracted


# -----------------------------------------------------------------------
# Confirmation keywords
# -----------------------------------------------------------------------

# Intent detection — words that signal the user wants a specific service
_ACCOUNT_WORDS = {"cuenta", "bancarizar", "registro", "registrar", "tarjeta"}
_LOAN_WORDS = {"préstamo", "prestamo", "crédito", "credito", "microcrédito",
               "microcredito", "plata", "financiamiento", "dinero"}
_SERVICE_INTENT_WORDS = _ACCOUNT_WORDS | _LOAN_WORDS


def _has_service_intent(text: str) -> bool:
    """Return True if the message signals the user wants to open an account or loan."""
    words = set(re.split(r"\W+", text.lower()))
    # Direct word match
    if words & _SERVICE_INTENT_WORDS:
        return True
    # Phrase patterns
    lower = text.lower()
    phrases = ("abrir", "solicitar", "pedir", "necesito", "quiero", "quisiera")
    targets = ("cuenta", "crédito", "credito", "préstamo", "prestamo", "plata")
    for phrase in phrases:
        if phrase in lower:
            for target in targets:
                if target in lower:
                    return True
    return False


_YES_WORDS = {"sí", "si", "correcto", "exacto", "ok", "dale", "claro", "listo",
              "confirmo", "está bien", "esta bien", "eso es", "afirmativo", "yes",
              "perfecto", "bien", "bueno", "vale", "eso", "así", "asi", "sip",
              "sep", "ajá", "aja", "obvio", "por supuesto", "de una"}
_NO_WORDS = {"no", "nop", "nel", "incorrecto", "mal", "error", "cambiar", "corregir"}


def _is_affirmative(text: str) -> bool | None:
    """Check if text is affirmative, negative, or ambiguous (None)."""
    lower = text.strip().lower().rstrip(".,!?")
    # Check NO_WORDS first — prevents "si" substring matching inside "incorrecto"
    if lower in _NO_WORDS:
        return False
    if lower in _YES_WORDS:
        return True
    # Word-boundary matching for multi-word inputs
    words = set(re.split(r"\s+", lower))
    if words & _NO_WORDS:
        return False
    if words & _YES_WORDS:
        return True
    return None


# -----------------------------------------------------------------------
# OnboardingAgent
# -----------------------------------------------------------------------

class OnboardingAgent(BaseAgent):
    """Conversational onboarding agent with state machine.

    The agent manages state in context["onboarding_state"] and collected data
    in context["onboarding_data"]. The LLM generates the conversational
    wrapper, while the state machine controls flow and tool execution.
    """

    name = "onboarding"
    system_prompt = _SYSTEM_PROMPT
    tools = _TOOLS
    _tool_handlers = {}  # Overridden in __init__

    def __init__(self, llm: LLMProvider, ml_client=None):
        super().__init__(llm)
        self._ml_client = ml_client

        # Register tool handlers
        self._tool_handlers = {
            "check_credit_score": self._handle_check_credit,
            "create_account": self._handle_create_account,
            "enable_helpyy_hand": self._handle_enable_helpyy,
        }

    # ------------------------------------------------------------------
    # Main process — state machine driven
    # ------------------------------------------------------------------

    async def process(self, message: str, context: dict, *, original_message: str | None = None) -> AgentResponse:
        """General assistant for pre-bancarization users.

        Data collection is now handled by the widget's inline form
        (/api/v1/onboarding/create-account), so this agent just answers
        questions and guides users toward the form.
        """
        logger.info("[ONBOARDING] general msg=%.60s", message[:60])

        content = await self._llm_respond(message, context, "")
        return self._respond(content, context, suggested_actions=["Abrir mi cuenta", "Ver productos BBVA", "¿Cómo funciona el microcrédito?"])

    async def process_stream(self, message: str, context: dict, *, original_message: str | None = None):
        # Streaming not supported for stateful agent — fall back to non-stream
        response = await self.process(message, context, original_message=original_message)
        yield response.content

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    async def _handle_greeting(self, message: str, context: dict, data: dict) -> AgentResponse:
        # If user already provided all data in one message, jump straight to confirmation
        if data.get("name") and data.get("cedula") and data.get("income"):
            context["onboarding_state"] = OnboardingState.CONFIRMING
            return await self._handle_confirming(message, context, data)

        # Detect if user is asking for a specific service (account / loan)
        if _has_service_intent(message):
            context["onboarding_state"] = OnboardingState.COLLECTING_DATA
            if data.get("name"):
                missing = self._missing_fields(data)
                content = await self._llm_respond(
                    message, context,
                    f"[ESTADO: El usuario quiere abrir cuenta o solicitar crédito. "
                    f"Ya tenemos su nombre. Faltan: {', '.join(missing)}. "
                    f"Pide los datos faltantes de forma natural.]",
                )
            else:
                content = await self._llm_respond(
                    message, context,
                    "[ESTADO: El usuario quiere abrir cuenta o solicitar un microcrédito. "
                    "Indícale brevemente que necesitas 3 datos rápidos: nombre completo, "
                    "número de cédula e ingreso mensual aproximado. Empieza pidiendo el nombre.]",
                )
            return self._respond(content, context)

        # No service intent — greet as general assistant, present available services
        # Stay in GREETING so subsequent messages also pass through intent detection
        content = await self._llm_respond(
            message, context,
            "[ESTADO: Interacción general, el usuario no ha pedido nada específico todavía. "
            "Saluda cálidamente, preséntate como Helpyy Hand de BBVA Colombia. "
            "Menciona brevemente que puedes ayudar con: 1) Abrir cuenta bancaria, "
            "2) Solicitar microcrédito, 3) Consultar productos BBVA. "
            "NO pidas ningún dato personal. Espera que el usuario diga qué necesita.]",
        )
        return self._respond(content, context, suggested_actions=[
            "Abrir mi cuenta", "Solicitar microcrédito", "Ver productos BBVA",
        ])

    async def _handle_collecting(self, message: str, context: dict, data: dict) -> AgentResponse:
        # If user changes mind and asks something unrelated, go back to general mode
        if not _has_service_intent(message) and not self._missing_fields(data) == [] and not any([
            data.get("name"), data.get("cedula"), data.get("income"),
        ]):
            context["onboarding_state"] = OnboardingState.GREETING
            return await self._handle_greeting(message, context, data)

        missing = self._missing_fields(data)

        if not missing:
            # All data collected — move to confirmation
            context["onboarding_state"] = OnboardingState.CONFIRMING
            name = data.get("name", "usuario")
            cedula = f"****{data['cedula'][-4:]}"
            income = f"${data['income']:,.0f}"
            content = await self._llm_respond(
                message, context,
                f"[ESTADO: Datos completos. Confirma con el usuario: "
                f"nombre={name}, cédula terminada en {cedula}, ingreso={income} COP. "
                f"Pregunta si los datos son correctos.]",
            )
            return self._respond(content, context)

        # Still need data
        collected_str = ", ".join(f"{k}={v}" for k, v in data.items())
        content = await self._llm_respond(
            message, context,
            f"[ESTADO: Datos recolectados: {collected_str or 'ninguno'}. "
            f"Faltan: {', '.join(missing)}. Pide lo que falta de forma conversacional, "
            f"no como formulario. Si el usuario dio algo nuevo, agradece.]",
        )
        return self._respond(content, context)

    async def _handle_confirming(self, message: str, context: dict, data: dict) -> AgentResponse:
        affirmative = _is_affirmative(message)

        if affirmative is True:
            # User confirmed — proceed to evaluation
            context["onboarding_state"] = OnboardingState.EVALUATING
            return await self._handle_evaluating(message, context, data)

        elif affirmative is False:
            # User wants to correct — go back to collecting
            context["onboarding_state"] = OnboardingState.COLLECTING_DATA
            content = await self._llm_respond(
                message, context,
                "[ESTADO: El usuario quiere corregir datos. "
                "Pregunta qué dato quiere cambiar de forma amable.]",
            )
            return self._respond(content, context)

        else:
            # Ambiguous — if all data is already complete, treat as confirmation
            # to avoid infinite loops where the LLM generates ambiguous responses
            if data.get("name") and data.get("cedula") and data.get("income"):
                context["onboarding_state"] = OnboardingState.EVALUATING
                return await self._handle_evaluating(message, context, data)

            # Truly ambiguous and data incomplete — ask again
            name = data.get("name", "???")
            cedula = f"****{data['cedula'][-4:]}" if data.get("cedula") else "???"
            income = f"${data['income']:,.0f}" if data.get("income") else "???"
            content = await self._llm_respond(
                message, context,
                f"[ESTADO: No quedó claro si confirmas. Datos: "
                f"nombre={name}, cédula={cedula}, ingreso={income}. "
                f"Pregunta claramente si son correctos.]",
            )
            return self._respond(content, context)

    async def _handle_evaluating(self, message: str, context: dict, data: dict) -> AgentResponse:
        """Run credit check, create account, and activate Helpyy — all in one step.

        The user already confirmed their data at CONFIRMING, so we proceed automatically.
        We never ask again "do you want to open the account?" — that's a dead-end with
        a local LLM that tends to hallucinate mid-flow.
        """
        # 1. Credit check
        logger.info("[ONBOARDING] EVALUATING → check_credit_score income=%s", data.get("income"))
        result = await self._tool_check_credit(data)
        logger.info("[ONBOARDING] Credit result: eligible=%s band=%s", result.get("eligible"), result.get("score_band"))
        context["prediction_result"] = result
        eligible = result.get("eligible", False)
        context["credit_eligible"] = eligible

        # 2. Always create account
        logger.info("[ONBOARDING] Creating account for user")
        account = await self._tool_create_account(data)
        logger.info("[ONBOARDING] Account created: %s", account["account_id"])
        context["account_id"] = account["account_id"]

        # 3. Always activate Helpyy Hand
        await self._tool_enable_helpyy(account["account_id"])
        context["helpyy_enabled"] = True
        context["onboarding_state"] = OnboardingState.DONE

        first_name = (data.get("name") or "").split()[0]

        if eligible:
            max_amount = result.get("max_amount", 0)
            product = result.get("recommended_product", "nano")
            content = await self._llm_respond(
                message, context,
                f"[ESTADO: ÉXITO TOTAL. Cuenta abierta (ID interno procesado). "
                f"Helpyy Hand activado. Además, el usuario CALIFICA para un "
                f"{product}crédito de hasta ${max_amount:,.0f} COP. "
                f"Felicita efusivamente. Dile que su cuenta ya está lista y activa. "
                f"Menciona que puede usar la app de BBVA para acceder a todos sus servicios. "
                f"NUNCA menciones el score numérico ni IDs internos.]",
            )
            return self._respond(content, context, metadata={
                "helpyy_enabled": True,
                "account_id": account["account_id"],
                "display_name": first_name,
            })
        else:
            factors = result.get("factors", [])
            factor_names = [f.get("name", "") for f in factors[:3]]
            context["rejection_factors"] = factor_names
            logger.info("[ONBOARDING] credit_eligible=False → account still opened, handoff to financial_advisor")
            content = await self._llm_respond(
                message, context,
                f"[ESTADO: ÉXITO PARCIAL. Cuenta abierta y Helpyy Hand activado. "
                f"Sin embargo, el usuario AÚN NO califica para microcrédito. "
                f"Factores que afectan: {factor_names}. "
                f"Celebra la apertura de la cuenta con mucho entusiasmo. "
                f"Dile que Helpyy Hand ya está activo y lo acompañará con un plan personalizado "
                f"para que pronto califique al crédito. Mucho ánimo y motivación. "
                f"NUNCA menciones scores ni variables del modelo.]",
            )
            return self._respond(
                content, context,
                handoff_to="financial_advisor",
                suggested_actions=["Ver mi plan de mejora", "Activar monitoreo"],
                metadata={
                    "helpyy_enabled": True,
                    "account_id": account["account_id"],
                    "display_name": first_name,
                    "rejection_factors": factor_names,
                },
            )

    async def _handle_account_opening(self, message: str, context: dict, data: dict) -> AgentResponse:
        # Fallback: this state is no longer part of the normal flow (evaluating handles
        # account creation directly). If we land here, auto-proceed to evaluating.
        context["onboarding_state"] = OnboardingState.EVALUATING
        return await self._handle_evaluating(message, context, data)

    async def _handle_helpyy_activation(self, message: str, context: dict, data: dict) -> AgentResponse:
        # Fallback: this state is no longer part of the normal flow (evaluating handles
        # Helpyy activation directly). If we land here, auto-proceed to evaluating
        # only if account hasn't been created yet; otherwise go to DONE.
        if not context.get("account_id"):
            context["onboarding_state"] = OnboardingState.EVALUATING
            return await self._handle_evaluating(message, context, data)
        # Account exists — emit final metadata and complete
        context["onboarding_state"] = OnboardingState.DONE
        first_name = (data.get("name") or "").split()[0]
        return self._respond(
            "¡Tu cuenta ya está activa y Helpyy Hand listo para acompañarte! ¿En qué más puedo ayudarte?",
            context,
            metadata={
                "helpyy_enabled": True,
                "account_id": context["account_id"],
                "display_name": first_name,
            },
        )

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    async def _tool_check_credit(self, data: dict) -> dict:
        """Call ML service or return mock result."""
        if self._ml_client:
            from backend.ml_client.schemas import RiskRequest
            request = RiskRequest(
                declared_income=data.get("income", 1_000_000),
                is_banked=0,
                employment_type="informal",
                age=30,
                city_type="urban",
                total_sessions=0,
                pct_conversion=0.0,
                tx_income_pct=0.0,
                payments_count=0,
                on_time_rate=0.5,
                overdue_rate=0.0,
                avg_decision_score=0.5,
            )
            pred = await self._ml_client.predict(request)
            return {
                "eligible": pred.eligible,
                "max_amount": pred.max_amount,
                "recommended_product": pred.recommended_product.value if pred.recommended_product else None,
                "score_band": pred.score_band.value,
                "factors": [{"name": f.name, "impact": f.impact, "weight": f.weight} for f in pred.factors],
            }

        # Mock fallback when no ML client configured
        income = data.get("income", 0)
        eligible = income >= 1_200_000
        return {
            "eligible": eligible,
            "max_amount": min(income * 2, 2_000_000) if eligible else None,
            "recommended_product": "micro" if eligible and income > 1_500_000 else "nano" if eligible else None,
            "score_band": "low_risk" if eligible else "high_risk",
            "factors": [
                {"name": "declared_income", "impact": "positive" if income > 1_000_000 else "negative", "weight": 0.2},
                {"name": "is_banked", "impact": "negative", "weight": 0.2},
            ],
        }

    async def _tool_create_account(self, data: dict) -> dict:
        """Simulate account creation. Returns account_id."""
        account_id = f"ACC-{uuid.uuid4().hex[:8].upper()}"
        return {
            "account_id": account_id,
            "status": "active",
            "name": data.get("name", ""),
        }

    async def _tool_enable_helpyy(self, account_id: str) -> dict:
        """Simulate enabling Helpyy Hand."""
        return {
            "account_id": account_id,
            "helpyy_enabled": True,
        }

    # Tool handlers called by BaseAgent._run_with_tools (if LLM-driven tools are used)
    async def _handle_check_credit(self, context: dict, **kwargs) -> str:
        data = context.get("onboarding_data", {})
        data.update(kwargs)
        result = await self._tool_check_credit(data)
        return json.dumps(result)

    async def _handle_create_account(self, context: dict, **kwargs) -> str:
        data = context.get("onboarding_data", {})
        data.update(kwargs)
        result = await self._tool_create_account(data)
        context["account_id"] = result["account_id"]
        return json.dumps(result)

    async def _handle_enable_helpyy(self, context: dict, **kwargs) -> str:
        account_id = kwargs.get("account_id", context.get("account_id", "unknown"))
        result = await self._tool_enable_helpyy(account_id)
        return json.dumps(result)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _missing_fields(data: dict) -> list[str]:
        """Return list of missing required fields."""
        missing = []
        if not data.get("name"):
            missing.append("nombre")
        if not data.get("cedula"):
            missing.append("cédula")
        if not data.get("income"):
            missing.append("ingreso mensual")
        return missing

    async def _llm_respond(self, message: str, context: dict, state_instruction: str) -> str:
        """Call LLM with system prompt + history + state instruction + user message."""
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

    def _respond(
        self,
        content: str,
        context: dict,
        handoff_to: str | None = None,
        suggested_actions: list[str] | None = None,
        metadata: dict | None = None,
    ) -> AgentResponse:
        return AgentResponse(
            content=content,
            agent_name=self.name,
            agent_type="onboarding",
            suggested_actions=suggested_actions or [],
            handoff_to=handoff_to,
            metadata={
                "state": context.get("onboarding_state", "unknown"),
                **(metadata or {}),
            },
        )

    def _agent_type(self) -> str:
        return "onboarding"
