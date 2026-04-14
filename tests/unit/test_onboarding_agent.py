"""Tests for the onboarding agent — state machine, data extraction, and full flows."""

import pytest
from unittest.mock import AsyncMock

from backend.agents.onboarding_agent import (
    OnboardingAgent,
    OnboardingState,
    extract_data_from_message,
    _is_affirmative,
    _parse_income,
)
from backend.agents.base_agent import AgentResponse


# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------

@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="Respuesta del agente.")
    llm.generate_stream = AsyncMock()
    return llm


@pytest.fixture
def agent(mock_llm):
    return OnboardingAgent(mock_llm)


@pytest.fixture
def fresh_context():
    """Fresh context with no state."""
    return {"history": []}


@pytest.fixture
def collecting_context():
    """Context already in COLLECTING_DATA state."""
    return {
        "history": [],
        "onboarding_state": OnboardingState.COLLECTING_DATA,
        "onboarding_data": {},
    }


@pytest.fixture
def full_data_context():
    """Context with all data collected, ready to confirm."""
    return {
        "history": [],
        "onboarding_state": OnboardingState.CONFIRMING,
        "onboarding_data": {
            "name": "Juan Pérez",
            "cedula": "1234567890",
            "income": 2_000_000,
        },
    }


# =======================================================================
# DATA EXTRACTION
# =======================================================================

class TestDataExtraction:

    def test_extracts_name_from_soy(self):
        data = extract_data_from_message("soy Juan Pérez")
        assert data["name"] == "Juan Pérez"

    def test_extracts_name_from_me_llamo(self):
        data = extract_data_from_message("me llamo María García")
        assert data["name"] == "María García"

    def test_extracts_name_from_mi_nombre_es(self):
        data = extract_data_from_message("mi nombre es Carlos López")
        assert data["name"] == "Carlos López"

    def test_extracts_cedula_8_digits(self):
        data = extract_data_from_message("mi cédula es 12345678")
        assert data["cedula"] == "12345678"

    def test_extracts_cedula_10_digits(self):
        data = extract_data_from_message("cc 1234567890")
        assert data["cedula"] == "1234567890"

    def test_extracts_income_with_keyword(self):
        data = extract_data_from_message("mi ingreso es 1500000")
        assert data["income"] == 1_500_000

    def test_extracts_income_millones(self):
        data = extract_data_from_message("gano 1.5 millones al mes")
        assert data["income"] == 1_500_000

    def test_extracts_income_mil(self):
        data = extract_data_from_message("gano 800 mil mensuales")
        assert data["income"] == 800_000

    def test_extracts_multiple_fields(self):
        data = extract_data_from_message(
            "soy Juan Pérez, mi cédula es 1234567890 y gano 2 millones"
        )
        assert data["name"] == "Juan Pérez"
        assert data["cedula"] == "1234567890"
        assert data["income"] == 2_000_000

    def test_extracts_all_in_messy_message(self):
        """The 'messy input' test case from requirements."""
        data = extract_data_from_message(
            "soy juan y mi cc es 12345678 gano 1500000 al mes"
        )
        assert "name" in data
        assert data["cedula"] == "12345678"
        assert data["income"] == 1_500_000

    def test_no_data_returns_empty(self):
        data = extract_data_from_message("hola buenos días")
        assert data == {}

    def test_ignores_short_numbers(self):
        data = extract_data_from_message("tengo 3 hijos")
        assert "cedula" not in data
        assert "income" not in data

    def test_income_large_standalone_number(self):
        data = extract_data_from_message("mis ingresos son de 2500000")
        assert data["income"] == 2_500_000


class TestParseIncome:

    def test_plain_number(self):
        assert _parse_income("ingreso 1500000") == 1_500_000

    def test_millones(self):
        assert _parse_income("gano 2 millones") == 2_000_000

    def test_mil(self):
        assert _parse_income("gano 800 mil") == 800_000

    def test_decimal_millones(self):
        assert _parse_income("1.5 millones") == 1_500_000

    def test_no_income(self):
        assert _parse_income("hola cómo estás") is None

    def test_small_number_ignored(self):
        assert _parse_income("tengo 3 gatos") is None


class TestIsAffirmative:

    def test_si(self):
        assert _is_affirmative("sí") is True

    def test_correcto(self):
        assert _is_affirmative("correcto") is True

    def test_dale(self):
        assert _is_affirmative("dale") is True

    def test_no(self):
        assert _is_affirmative("no") is False

    def test_incorrecto(self):
        assert _is_affirmative("incorrecto") is False

    def test_ambiguous(self):
        assert _is_affirmative("no sé, creo que sí") is None or _is_affirmative("quizás") is None


# =======================================================================
# STATE MACHINE
# =======================================================================

class TestStateMachine:

    @pytest.mark.asyncio
    async def test_starts_in_greeting(self, agent, fresh_context):
        response = await agent.process("hola", fresh_context)
        assert isinstance(response, AgentResponse)
        assert response.agent_type == "onboarding"

    @pytest.mark.asyncio
    async def test_greeting_transitions_to_collecting(self, agent, fresh_context):
        await agent.process("hola", fresh_context)
        assert fresh_context["onboarding_state"] in (
            OnboardingState.COLLECTING_DATA,
            OnboardingState.CONFIRMING,
        )

    @pytest.mark.asyncio
    async def test_greeting_with_name_skips_ahead(self, agent, fresh_context):
        await agent.process("soy Juan Pérez", fresh_context)
        assert fresh_context["onboarding_data"]["name"] == "Juan Pérez"
        assert fresh_context["onboarding_state"] == OnboardingState.COLLECTING_DATA

    @pytest.mark.asyncio
    async def test_greeting_with_all_data_jumps_to_confirming(self, agent, fresh_context):
        await agent.process(
            "soy Juan Pérez, cédula 1234567890 y gano 2 millones", fresh_context,
        )
        assert fresh_context["onboarding_state"] == OnboardingState.CONFIRMING

    @pytest.mark.asyncio
    async def test_collecting_asks_for_missing(self, agent, collecting_context):
        collecting_context["onboarding_data"]["name"] = "Juan"
        await agent.process("ya te di mi nombre", collecting_context)
        # Should still be collecting (missing cedula and income)
        assert collecting_context["onboarding_state"] == OnboardingState.COLLECTING_DATA

    @pytest.mark.asyncio
    async def test_collecting_moves_to_confirming_when_complete(self, agent, collecting_context):
        collecting_context["onboarding_data"]["name"] = "Juan"
        collecting_context["onboarding_data"]["cedula"] = "12345678"
        await agent.process("gano 2 millones al mes", collecting_context)
        assert collecting_context["onboarding_state"] == OnboardingState.CONFIRMING

    @pytest.mark.asyncio
    async def test_confirming_yes_moves_to_evaluating(self, agent, full_data_context):
        await agent.process("sí, correcto", full_data_context)
        # Should have moved through EVALUATING
        assert full_data_context["onboarding_state"] in (
            OnboardingState.ACCOUNT_OPENING,
            OnboardingState.DONE,
        )

    @pytest.mark.asyncio
    async def test_confirming_no_goes_back_to_collecting(self, agent, full_data_context):
        await agent.process("no, está mal", full_data_context)
        assert full_data_context["onboarding_state"] == OnboardingState.COLLECTING_DATA


# =======================================================================
# HAPPY PATH — full conversation
# =======================================================================

class TestOnboardingHappyPath:

    @pytest.mark.asyncio
    async def test_full_happy_path(self, mock_llm):
        """Complete flow: greeting → data → confirm → approved → account → helpyy."""
        agent = OnboardingAgent(mock_llm)
        ctx = {"history": []}

        # Track LLM calls to return appropriate responses
        mock_llm.generate.return_value = "Bienvenido a BBVA!"

        # Step 1: Greeting
        r1 = await agent.process("hola", ctx)
        assert r1.agent_type == "onboarding"

        # Step 2: User gives all data at once
        r2 = await agent.process(
            "soy María García, cédula 1098765432 y gano 3 millones", ctx,
        )
        assert ctx["onboarding_data"]["name"] == "María García"
        assert ctx["onboarding_data"]["cedula"] == "1098765432"
        assert ctx["onboarding_data"]["income"] == 3_000_000
        assert ctx["onboarding_state"] == OnboardingState.CONFIRMING

        # Step 3: Confirm
        r3 = await agent.process("sí, todo correcto", ctx)
        # Should be approved (income 3M > 1.2M threshold in mock)
        assert ctx["prediction_result"]["eligible"] is True
        assert ctx["onboarding_state"] == OnboardingState.ACCOUNT_OPENING

        # Step 4: Open account
        r4 = await agent.process("sí, quiero abrir la cuenta", ctx)
        assert "account_id" in ctx
        assert ctx["onboarding_state"] == OnboardingState.HELPYY_ACTIVATION

        # Step 5: Activate Helpyy
        r5 = await agent.process("dale, actívalo", ctx)
        assert ctx["onboarding_state"] == OnboardingState.DONE
        assert ctx.get("helpyy_enabled") is True

    @pytest.mark.asyncio
    async def test_incremental_data_collection(self, mock_llm):
        """User provides data across multiple messages."""
        agent = OnboardingAgent(mock_llm)
        ctx = {"history": []}
        mock_llm.generate.return_value = "Gracias!"

        # Greeting
        await agent.process("hola buenos días", ctx)
        assert ctx["onboarding_state"] == OnboardingState.COLLECTING_DATA

        # Name
        await agent.process("me llamo Carlos López", ctx)
        assert ctx["onboarding_data"]["name"] == "Carlos López"
        assert ctx["onboarding_state"] == OnboardingState.COLLECTING_DATA

        # Cedula
        await agent.process("mi cédula es 87654321", ctx)
        assert ctx["onboarding_data"]["cedula"] == "87654321"
        assert ctx["onboarding_state"] == OnboardingState.COLLECTING_DATA

        # Income — completes the data
        await agent.process("gano 1.5 millones", ctx)
        assert ctx["onboarding_data"]["income"] == 1_500_000
        assert ctx["onboarding_state"] == OnboardingState.CONFIRMING


# =======================================================================
# REJECTION PATH
# =======================================================================

class TestOnboardingRejection:

    @pytest.mark.asyncio
    async def test_rejection_gives_empathetic_response(self, mock_llm):
        """Low-income user gets rejected with empathy and handoff."""
        agent = OnboardingAgent(mock_llm)
        ctx = {"history": []}
        mock_llm.generate.return_value = "Respuesta empática del agente."

        # Give all data at once — low income
        await agent.process(
            "soy Pedro Ruiz, cédula 11223344 y gano 500 mil", ctx,
        )
        # Confirm
        r = await agent.process("sí", ctx)

        # Should be rejected (income 500K < 1.2M threshold)
        assert ctx["prediction_result"]["eligible"] is False
        assert r.handoff_to == "financial_advisor"
        assert ctx["onboarding_state"] == OnboardingState.DONE

    @pytest.mark.asyncio
    async def test_rejection_includes_factors(self, mock_llm):
        """Rejection response should include factor metadata for handoff."""
        agent = OnboardingAgent(mock_llm)
        ctx = {"history": []}
        mock_llm.generate.return_value = "Te ayudaremos a mejorar."

        await agent.process("soy Ana, cc 99887766, gano 400 mil", ctx)
        r = await agent.process("correcto", ctx)

        assert "rejection_factors" in r.metadata
        assert isinstance(r.metadata["rejection_factors"], list)


# =======================================================================
# MESSY INPUT
# =======================================================================

class TestOnboardingMessyInput:

    @pytest.mark.asyncio
    async def test_all_data_in_one_messy_message(self, mock_llm):
        """'soy juan y mi cc es 12345678 gano 1500000'"""
        agent = OnboardingAgent(mock_llm)
        ctx = {"history": []}
        mock_llm.generate.return_value = "Confirmemos tus datos."

        await agent.process(
            "soy juan y mi cc es 12345678 gano 1500000 al mes", ctx,
        )
        data = ctx["onboarding_data"]
        assert data.get("name")  # "juan" extracted
        assert data["cedula"] == "12345678"
        assert data["income"] == 1_500_000
        # Should jump directly to confirming
        assert ctx["onboarding_state"] == OnboardingState.CONFIRMING

    @pytest.mark.asyncio
    async def test_name_and_cedula_same_message(self, mock_llm):
        agent = OnboardingAgent(mock_llm)
        ctx = {"history": []}
        mock_llm.generate.return_value = "Gracias!"

        await agent.process("hola", ctx)
        await agent.process("me llamo Ana Torres, mi cc es 98765432", ctx)
        data = ctx["onboarding_data"]
        assert data["name"] == "Ana Torres"
        assert data["cedula"] == "98765432"

    @pytest.mark.asyncio
    async def test_income_in_different_formats(self, mock_llm):
        """Agent handles various income formats."""
        agent = OnboardingAgent(mock_llm)

        for msg, expected in [
            ("gano 1500000", 1_500_000),
            ("gano 1.5 millones", 1_500_000),
            ("gano 800 mil", 800_000),
            ("gano 2 millones al mes", 2_000_000),
        ]:
            ctx = {
                "history": [],
                "onboarding_state": OnboardingState.COLLECTING_DATA,
                "onboarding_data": {"name": "Test", "cedula": "12345678"},
            }
            mock_llm.generate.return_value = "Confirmemos."
            await agent.process(msg, ctx)
            assert ctx["onboarding_data"]["income"] == expected, f"Failed for: {msg}"

    @pytest.mark.asyncio
    async def test_correction_flow(self, mock_llm):
        """User says 'no' at confirmation, corrects data, re-confirms."""
        agent = OnboardingAgent(mock_llm)
        ctx = {
            "history": [],
            "onboarding_state": OnboardingState.CONFIRMING,
            "onboarding_data": {
                "name": "Juan",
                "cedula": "12345678",
                "income": 1_500_000,
            },
        }
        mock_llm.generate.return_value = "Qué quieres corregir?"

        # Say no
        await agent.process("no, está mal", ctx)
        assert ctx["onboarding_state"] == OnboardingState.COLLECTING_DATA

        # Provide corrected name
        await agent.process("me llamo Juan Carlos Pérez", ctx)
        assert ctx["onboarding_data"]["name"] == "Juan Carlos Pérez"

    @pytest.mark.asyncio
    async def test_user_declines_account(self, mock_llm):
        """User approved but doesn't want to open account now."""
        agent = OnboardingAgent(mock_llm)
        ctx = {
            "history": [],
            "onboarding_state": OnboardingState.ACCOUNT_OPENING,
            "onboarding_data": {"name": "Test", "cedula": "12345678", "income": 2_000_000},
            "prediction_result": {"eligible": True},
        }
        mock_llm.generate.return_value = "Está bien, vuelve cuando quieras."
        r = await agent.process("no, ahora no", ctx)
        assert ctx["onboarding_state"] == OnboardingState.DONE

    @pytest.mark.asyncio
    async def test_user_declines_helpyy(self, mock_llm):
        """User opens account but declines Helpyy Hand."""
        agent = OnboardingAgent(mock_llm)
        ctx = {
            "history": [],
            "onboarding_state": OnboardingState.HELPYY_ACTIVATION,
            "onboarding_data": {"name": "Test", "cedula": "12345678", "income": 2_000_000},
            "account_id": "ACC-TEST123",
        }
        mock_llm.generate.return_value = "Puedes activarlo después."
        r = await agent.process("no gracias", ctx)
        assert ctx["onboarding_state"] == OnboardingState.DONE
        assert not ctx.get("helpyy_enabled")


# =======================================================================
# ML CLIENT INTEGRATION
# =======================================================================

class TestOnboardingWithMLClient:

    @pytest.mark.asyncio
    async def test_uses_ml_client_when_available(self, mock_llm):
        """When ml_client is provided, it should be used for scoring."""
        mock_ml = AsyncMock()
        mock_prediction = AsyncMock()
        mock_prediction.eligible = True
        mock_prediction.max_amount = 1_000_000
        mock_prediction.recommended_product = AsyncMock()
        mock_prediction.recommended_product.value = "nano"
        mock_prediction.score_band = AsyncMock()
        mock_prediction.score_band.value = "medium_risk"
        mock_prediction.factors = []
        mock_ml.predict = AsyncMock(return_value=mock_prediction)

        agent = OnboardingAgent(mock_llm, ml_client=mock_ml)
        ctx = {
            "history": [],
            "onboarding_state": OnboardingState.CONFIRMING,
            "onboarding_data": {
                "name": "Test User",
                "cedula": "12345678",
                "income": 2_000_000,
            },
        }
        mock_llm.generate.return_value = "Felicitaciones!"

        await agent.process("sí, confirmo", ctx)
        mock_ml.predict.assert_called_once()
        assert ctx["prediction_result"]["eligible"] is True
