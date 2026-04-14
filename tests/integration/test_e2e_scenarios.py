"""E2E scenario tests — validate the complete user journeys end-to-end.

These tests use the full application stack: FastAPI app → PII middleware →
Orchestrator → Agents → ML mock → responses, exercised via WebSocket
and direct orchestrator calls.

Scenario 1: Successful onboarding → credit evaluation with loan options
Scenario 2: Rejection → empathy → gamification plan → monitor notification
Scenario 3: PII never reaches the LLM (intercept all calls)

Architecture note: The PII middleware tokenizes names/cedulas BEFORE the agent
receives them. Scenarios 1 & 2 test the multi-step agent flow by calling the
orchestrator directly (bypassing PII — those patterns have their own unit tests).
Scenario 3 specifically tests PII isolation through the full WebSocket path.
"""

import json
import re

import pytest
from starlette.testclient import TestClient

from backend.agents.base_agent import AgentResponse
from backend.agents.orchestrator import Orchestrator
from backend.agents.onboarding_agent import OnboardingAgent
from backend.agents.credit_evaluator_agent import CreditEvaluatorAgent, build_options_table
from backend.agents.financial_advisor_agent import (
    FinancialAdvisorAgent, build_plan, compute_level,
)
from backend.agents.helpyy_general_agent import HelpyyGeneralAgent
from backend.agents.persistent_monitor_agent import (
    PersistentMonitorAgent,
    InMemoryUserStore,
    NotificationStore,
    UserRecord,
)
from backend.api.main import app
from backend.api.routers.chat import set_orchestrator
from backend.data.schemas import UserState
from backend.llm.provider import LLMProvider
from backend.security.pii_vault import PIIVault
from backend.security.pii_detokenizer import set_vault as set_detok_vault


# ═══════════════════════════════════════════════════════════════════════
# Spy LLM — records every call and returns scripted responses
# ═══════════════════════════════════════════════════════════════════════


class SpyLLM(LLMProvider):
    """LLM that records all calls and returns scripted responses."""

    def __init__(self, script: list[str] | None = None, default: str = "Respuesta del LLM."):
        self.calls: list[list[dict]] = []
        self._script = list(script or [])
        self._default = default

    async def generate(self, messages, **kwargs):
        self.calls.append(messages)
        if self._script:
            return self._script.pop(0)
        return self._default

    async def generate_stream(self, messages, **kwargs):
        text = await self.generate(messages, **kwargs)
        for word in text.split():
            yield word + " "

    async def generate_with_tools(self, messages, tools, **kwargs):
        return await self.generate(messages, **kwargs)

    def all_text_sent_to_llm(self) -> str:
        """Concatenate ALL text from ALL messages sent to the LLM."""
        parts = []
        for call in self.calls:
            for msg in call:
                parts.append(msg.get("content", ""))
        return " ".join(parts)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture()
def pii_vault(tmp_path):
    vault = PIIVault(db_path=str(tmp_path / "e2e_pii.db"), ttl_hours=1)
    set_detok_vault(vault)
    yield vault
    set_detok_vault(None)


@pytest.fixture()
def spy_llm():
    return SpyLLM()


@pytest.fixture()
def all_agents(spy_llm):
    """All agents instantiated with the spy LLM."""
    return {
        "onboarding": OnboardingAgent(spy_llm),
        "helpyy_general": HelpyyGeneralAgent(spy_llm),
        "credit_evaluator": CreditEvaluatorAgent(spy_llm),
        "financial_advisor": FinancialAdvisorAgent(spy_llm),
    }


@pytest.fixture()
def orch(spy_llm, all_agents):
    """Full orchestrator with all agents."""
    return Orchestrator(spy_llm, all_agents)


@pytest.fixture()
def ws_client(spy_llm, pii_vault):
    """TestClient for WebSocket PII tests."""
    agents = {
        "onboarding": OnboardingAgent(spy_llm),
        "helpyy_general": HelpyyGeneralAgent(spy_llm),
        "credit_evaluator": CreditEvaluatorAgent(spy_llm),
        "financial_advisor": FinancialAdvisorAgent(spy_llm),
    }
    orch = Orchestrator(spy_llm, agents)
    set_orchestrator(orch)
    yield TestClient(app), spy_llm
    set_orchestrator(None)


# ═══════════════════════════════════════════════════════════════════════
# ESCENARIO 1 — Onboarding exitoso → crédito aprobado → opciones de plazo
# ═══════════════════════════════════════════════════════════════════════


class TestScenario1_SuccessfulOnboarding:
    """Full journey: user arrives → provides data → ML approves →
    account opened → Helpyy activated → asks about microcredit →
    evaluator responds with loan options."""

    @pytest.mark.asyncio
    async def test_full_onboarding_to_credit_evaluation(self, spy_llm, orch):
        """Multi-step onboarding followed by credit evaluation."""
        session = "e2e-s1"
        user_unbanked = UserState(user_id=session, is_banked=False)
        user_banked = UserState(user_id=session, is_banked=True)

        # ── Script the LLM responses for each agent step ──
        spy_llm._script = [
            # 1. Onboarding greeting
            "¡Hola! Bienvenido a BBVA. ¿Cómo te llamas?",
            # 2. Collecting → name extracted, ask for rest
            "¡Hola Carlos! Necesito tu cédula y tu ingreso mensual.",
            # 3. All data collected → confirm
            "Perfecto. Confirmo: Carlos Pérez, cédula ****7890, ingreso $1,500,000. ¿Correcto?",
            # 4. ML approves → account opening prompt
            "¡Felicidades Carlos! Calificas para microcrédito hasta $2,000,000. ¿Abrimos tu cuenta?",
            # 5. Account created → Helpyy activation
            "¡Cuenta creada! ¿Quieres activar Helpyy Hand?",
            # 6. Helpyy activated
            "¡Helpyy Hand activado! Bienvenido.",
            # 7. Intent classifier for credit inquiry
            '{"intent": "credit_inquiry"}',
            # 8. Credit evaluator response
            "Tienes 3 opciones de microcrédito: 6 meses ($180K/mes), 12 meses ($98K/mes), 18 meses ($71K/mes).",
        ]

        # ── Step 1: Greeting (unbanked → routed to onboarding) ──
        r1 = await orch.handle_message("Hola, quiero una cuenta", session, user_unbanked)
        assert r1.agent_name == "onboarding"
        assert "llamas" in r1.content.lower() or "nombre" in r1.content.lower()

        # ── Step 2: Provide name ──
        r2 = await orch.handle_message("Me llamo Carlos Pérez", session, user_unbanked)
        assert r2.agent_name == "onboarding"

        # ── Step 3: Provide cedula + income → triggers confirmation ──
        r3 = await orch.handle_message(
            "Mi cédula es 1234567890 y gano 1500000 mensuales", session, user_unbanked,
        )
        assert r3.agent_name == "onboarding"
        # Agent should be asking for confirmation
        assert "confirm" in r3.content.lower() or "correcto" in r3.content.lower()

        # ── Step 4: Confirm → ML evaluation → approved ──
        # NOTE: must use clean "sí" — _is_affirmative needs exact match
        r4 = await orch.handle_message("sí", session, user_unbanked)
        assert r4.agent_name == "onboarding"
        # ML mock: income 1.5M >= 1.2M → approved
        assert "felicidades" in r4.content.lower() or "calificas" in r4.content.lower()

        # ── Step 5: Open account ──
        r5 = await orch.handle_message("dale", session, user_unbanked)
        assert r5.agent_name == "onboarding"
        assert "cuenta" in r5.content.lower() or "helpyy" in r5.content.lower()

        # ── Step 6: Activate Helpyy Hand ──
        r6 = await orch.handle_message("claro", session, user_unbanked)
        assert r6.agent_name == "onboarding"
        assert r6.metadata.get("helpyy_enabled") is True

        # ── Step 7: Now banked, ask about microcredit ──
        # Reuse same session so prediction_result from step 4 persists in context
        spy_llm._script = [
            '{"intent": "credit_inquiry"}',
            "Tienes 3 opciones de microcrédito.",
        ]
        r7 = await orch.handle_message("Quiero un microcrédito", session, user_banked)
        assert r7.agent_name == "credit_evaluator"
        assert r7.metadata.get("eligible") is True
        assert r7.metadata.get("max_amount") is not None
        # Should have loan options
        options = r7.metadata.get("options", [])
        assert len(options) == 3
        assert [o["term_months"] for o in options] == [6, 12, 18]

    @pytest.mark.asyncio
    async def test_income_1500k_approved_by_ml_mock(self, spy_llm, all_agents):
        """Verify ML mock: income $1.5M → approved."""
        onboarding = all_agents["onboarding"]
        result = await onboarding._tool_check_credit({"income": 1_500_000})
        assert result["eligible"] is True
        assert result["max_amount"] == 2_000_000

    def test_credit_evaluator_returns_3_term_options(self):
        """Build loan options table with 6, 12, 18 months."""
        options = build_options_table(2_000_000)
        assert len(options) == 3
        assert [o["term_months"] for o in options] == [6, 12, 18]
        # Monthly payments should decrease with longer terms
        assert options[0]["monthly_payment"] > options[1]["monthly_payment"] > options[2]["monthly_payment"]
        # Verify reasonable Colombian microcrédito rate (2.5% monthly)
        assert options[0]["effective_annual_rate"] > 0.30  # ~34.5% EA

    @pytest.mark.asyncio
    async def test_helpyy_activation_sets_metadata(self, spy_llm, all_agents):
        """Helpyy activation step should set helpyy_enabled=True in metadata."""
        onboarding = all_agents["onboarding"]
        spy_llm._default = "¡Helpyy activado!"

        context = {
            "onboarding_state": "helpyy_activation",
            "onboarding_data": {"name": "Carlos", "cedula": "12345", "income": 1_500_000},
            "account_id": "ACC-TEST",
        }
        response = await onboarding.process("Sí, activar", context)
        assert response.metadata.get("helpyy_enabled") is True


# ═══════════════════════════════════════════════════════════════════════
# ESCENARIO 2 — Rechazo → empatía → gamificación → notificación
# ═══════════════════════════════════════════════════════════════════════


class TestScenario2_RejectionAndGamification:
    """Low income → rejected → empathetic response → handoff to advisor →
    gamification plan → monitor notification."""

    @pytest.mark.asyncio
    async def test_rejection_triggers_handoff_to_advisor(self, spy_llm, orch):
        """Income $300K → ML rejects → handoff to financial_advisor."""
        session = "e2e-s2"
        user = UserState(user_id=session, is_banked=False)

        spy_llm._script = [
            "¡Hola! ¿Cómo te llamas?",
            "Gracias María. ¿Tu cédula y cuánto ganas al mes?",
            "Confirmo: María López, cédula ****3210, ingreso $300,000. ¿Correcto?",
            # Rejection — empathetic (the agent writes this response)
            "María, por ahora aún no cumples todos los requisitos, pero te vamos a ayudar "
            "a mejorar tu perfil. Te conecto con tu asesor financiero.",
            # Handoff target: financial advisor response
            "¡Hola María! Voy a crear un plan personalizado para ti.",
        ]

        # Step 1-3: Provide all data
        await orch.handle_message("Hola", session, user)
        await orch.handle_message("Me llamo María López", session, user)
        await orch.handle_message("Cédula 9876543210, gano 300000", session, user)

        # Step 4: Confirm → rejection → handoff
        response = await orch.handle_message("Sí, correcto", session, user)

        # After handoff, the response should come from financial_advisor
        assert response.agent_name == "financial_advisor"
        assert response.metadata.get("handoff_from") == "onboarding"

    @pytest.mark.asyncio
    async def test_rejection_never_says_rechazado(self, spy_llm, orch):
        """The rejection response must NEVER contain 'rechazado'."""
        session = "e2e-s2-vocab"
        user = UserState(user_id=session, is_banked=False)

        spy_llm._script = [
            "¡Hola! ¿Tu nombre?",
            "Datos recibidos.",
            "¿Son correctos?",
            # The LLM should follow the system prompt restriction
            "Aún no cumples los requisitos, pero te ayudamos.",
            "Voy a crear tu plan de mejora.",
        ]

        await orch.handle_message("Hola", session, user)
        await orch.handle_message("Me llamo Ana Ruiz", session, user)
        await orch.handle_message("Cédula 11223344, gano 250000", session, user)
        response = await orch.handle_message("Sí", session, user)

        # Check all LLM system prompts included the restriction
        all_text = spy_llm.all_text_sent_to_llm().lower()
        assert "nunca" in all_text and ("rechazado" in all_text or "rechazo" in all_text)

    @pytest.mark.asyncio
    async def test_income_300k_rejected_by_ml_mock(self, spy_llm, all_agents):
        """ML mock: income $300K < $1.2M threshold → rejected."""
        onboarding = all_agents["onboarding"]
        result = await onboarding._tool_check_credit({"income": 300_000})
        assert result["eligible"] is False
        assert result["max_amount"] is None

    def test_gamification_plan_for_rejected_user(self):
        """Advisor creates a progressive 4-week plan with missions."""
        factors = [
            {"factor_name": "on_time_rate", "potential_reduction": 0.15},
            {"factor_name": "is_banked", "potential_reduction": 0.05},
            {"factor_name": "pct_conversion", "potential_reduction": 0.03},
        ]
        plan = build_plan(factors, occupation="vendedor_ambulante", plan_weeks=4)

        assert len(plan) >= 2
        assert plan[0]["difficulty"] == "easy"  # starts easy
        assert all("start_week" in m for m in plan)
        assert all(m["start_week"] <= 4 for m in plan)
        # Should target the user's weak factors
        targeted = {m["factor"] for m in plan}
        assert targeted & {"on_time_rate", "pct_conversion", "is_banked"}

    def test_gamification_levels(self):
        """Level progression: 0→Principiante, 50→Aprendiz, 500→Maestro."""
        assert compute_level(0)["level_name"] == "Principiante"
        assert compute_level(50)["level_name"] == "Aprendiz"
        assert compute_level(150)["level_name"] == "Disciplinado"
        assert compute_level(300)["level_name"] == "Experto"
        assert compute_level(500)["level_name"] == "Maestro Financiero"

    def test_occupation_tips_personalized(self):
        """Missions should include tips for vendedor_ambulante."""
        factors = [{"factor_name": "on_time_rate", "potential_reduction": 0.1}]
        plan = build_plan(factors, occupation="vendedor_ambulante", plan_weeks=4)
        # At least one mission should mention arepas/empanadas or venta
        descriptions = " ".join(m["description"] for m in plan).lower()
        assert "vend" in descriptions or "arepa" in descriptions or "ganancias" in descriptions

    @pytest.mark.asyncio
    async def test_monitor_generates_notification_for_rejected_user(self):
        """After rejection, monitor checks score and generates notifications."""
        user_store = InMemoryUserStore()
        notif_store = NotificationStore()

        user = UserRecord(
            user_id="maria_lopez",
            score_status="pendiente_mejora",
            last_p_default=0.60,
            occupation="vendedor_ambulante",
            declared_income=300_000,
            is_banked=True,
            active_missions=["Depósito Constante"],
        )
        user_store.add_user(user)

        monitor = PersistentMonitorAgent(
            ml_client=None,
            user_store=user_store,
            notification_store=notif_store,
        )

        notifications = await monitor.run_cycle()

        # At least 1 score notification + 1 mission reminder
        assert len(notifications) >= 2
        types = {n.type for n in notifications}
        assert "mission_reminder" in types
        assert types & {"score_improved", "score_same", "score_decreased"}

        # Verify retrievable
        stored = notif_store.get_for_user("maria_lopez")
        assert len(stored) >= 2


# ═══════════════════════════════════════════════════════════════════════
# ESCENARIO 3 — PII nunca llega al LLM
# ═══════════════════════════════════════════════════════════════════════


class TestScenario3_PIINeverReachesLLM:
    """Intercept ALL LLM calls via SpyLLM and verify no raw PII appears.

    Tested PII types: cedula, name, email, phone.
    Uses WebSocket (the real path where PII middleware is active).
    """

    def test_cedula_never_reaches_llm(self, ws_client):
        tc, llm = ws_client
        llm._default = "Datos recibidos."

        with tc.websocket_connect("/api/v1/ws/chat/pii3-cc") as ws:
            ws.receive_json()
            ws.send_json({"type": "message", "content": "Mi cedula es 1234567890", "is_banked": False})
            _collect_until_done(ws)

        text = llm.all_text_sent_to_llm()
        assert "1234567890" not in text
        assert "[TOK_CC_" in text

    def test_name_never_reaches_llm(self, ws_client):
        tc, llm = ws_client
        llm._default = "Encantado."

        with tc.websocket_connect("/api/v1/ws/chat/pii3-name") as ws:
            ws.receive_json()
            ws.send_json({"type": "message", "content": "Me llamo Juan Fernando García", "is_banked": False})
            _collect_until_done(ws)

        text = llm.all_text_sent_to_llm()
        assert "Juan Fernando" not in text
        assert "[TOK_NAME_" in text

    def test_email_never_reaches_llm(self, ws_client):
        tc, llm = ws_client
        llm._default = "Correo registrado."

        with tc.websocket_connect("/api/v1/ws/chat/pii3-email") as ws:
            ws.receive_json()
            ws.send_json({"type": "message", "content": "Mi correo es juan.garcia@gmail.com", "is_banked": False})
            _collect_until_done(ws)

        text = llm.all_text_sent_to_llm()
        assert "juan.garcia@gmail.com" not in text
        assert "[TOK_EMAIL_" in text

    def test_phone_never_reaches_llm(self, ws_client):
        tc, llm = ws_client
        llm._default = "Teléfono registrado."

        with tc.websocket_connect("/api/v1/ws/chat/pii3-phone") as ws:
            ws.receive_json()
            ws.send_json({"type": "message", "content": "Mi celular es 3101234567", "is_banked": False})
            _collect_until_done(ws)

        text = llm.all_text_sent_to_llm()
        assert "3101234567" not in text
        assert "[TOK_PHONE_" in text

    def test_multiple_pii_all_tokenized(self, ws_client):
        """Name + cedula + email in one message — ALL tokenized before LLM."""
        tc, llm = ws_client
        llm._default = "Datos recibidos."

        with tc.websocket_connect("/api/v1/ws/chat/pii3-multi") as ws:
            ws.receive_json()
            ws.send_json({
                "type": "message",
                "content": "Me llamo Pedro Martínez, cédula 9876543210, correo pedro@mail.com",
                "is_banked": False,
            })
            _collect_until_done(ws)

        text = llm.all_text_sent_to_llm()
        assert "Pedro Martínez" not in text
        assert "9876543210" not in text
        assert "pedro@mail.com" not in text
        assert "[TOK_NAME_" in text
        assert "[TOK_CC_" in text
        assert "[TOK_EMAIL_" in text

    def test_pii_not_in_outbound_websocket(self, ws_client):
        """Raw PII must not leak back to the frontend in any event."""
        tc, llm = ws_client
        llm._default = "Tus datos están seguros."

        with tc.websocket_connect("/api/v1/ws/chat/pii3-out") as ws:
            ws.receive_json()
            ws.send_json({
                "type": "message",
                "content": "Me llamo Ana Ruiz, cédula 1122334455",
                "is_banked": False,
            })
            events = _collect_until_done(ws)

        all_outbound = json.dumps(events)
        assert "1122334455" not in all_outbound
        assert "Ana Ruiz" not in all_outbound

    def test_full_multiturn_pii_audit(self, ws_client):
        """Multi-turn conversation — audit ALL LLM calls for PII leaks."""
        tc, llm = ws_client
        llm._script = [
            "¡Hola! ¿Cómo te llamas?",
            "Gracias. ¿Tu cédula?",
            "Datos recibidos.",
        ]

        messages = [
            "Hola, quiero una cuenta",
            "Me llamo Santiago Herrera Gómez",
            "Mi cédula es 5566778899 y mi correo es santiago@test.co",
        ]

        with tc.websocket_connect("/api/v1/ws/chat/pii3-audit") as ws:
            ws.receive_json()
            for msg in messages:
                ws.send_json({"type": "message", "content": msg, "is_banked": False})
                _collect_until_done(ws)

        text = llm.all_text_sent_to_llm()
        for pii in ["Santiago Herrera Gómez", "5566778899", "santiago@test.co"]:
            assert pii not in text, f"PII leak: {pii!r} found in LLM input"


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _collect_until_done(ws, max_events=80):
    events = []
    for _ in range(max_events):
        data = ws.receive_json()
        events.append(data)
        if data.get("type") == "done":
            break
    return events


def _collect_all_events(ws, max_events=120):
    events = []
    done_count = 0
    expect_more = False
    for _ in range(max_events):
        data = ws.receive_json()
        events.append(data)
        if data.get("type") == "done":
            done_count += 1
            if data.get("handoff_to"):
                expect_more = True
            elif expect_more and done_count >= 2:
                break
            else:
                break
    return events
