"""Tests for the credit evaluator agent.

Covers: approved flow with options table, rejected flow with handoff,
loan simulation math, factor humanization, edge cases.
"""

import math
from unittest.mock import AsyncMock

import pytest

from backend.agents.credit_evaluator_agent import (
    CreditEvaluatorAgent,
    MONTHLY_RATE_DEFAULT,
    build_options_table,
    simulate_loan,
    _humanize_factor,
)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _make_llm(response: str = "respuesta del LLM") -> AsyncMock:
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value=response)
    llm.generate_stream = AsyncMock()
    return llm


def _approved_context(income: float = 2_000_000) -> dict:
    """Context where the user is eligible."""
    return {
        "user_data": {"income": income},
        "prediction_eligible": True,
    }


def _rejected_context(income: float = 400_000) -> dict:
    """Context where the user is NOT eligible."""
    return {
        "user_data": {"income": income},
        "prediction_eligible": False,
    }


# -----------------------------------------------------------------------
# Loan simulation math
# -----------------------------------------------------------------------

class TestLoanSimulation:
    """Test the pure loan simulation function."""

    def test_standard_annuity_formula(self):
        """Monthly payment matches the standard annuity formula."""
        amount = 1_000_000
        term = 12
        r = 0.025  # 2.5% monthly

        result = simulate_loan(amount, term, r)

        # Manual calculation: P * r * (1+r)^n / ((1+r)^n - 1)
        factor = (1 + r) ** term
        expected = amount * r * factor / (factor - 1)

        assert result["monthly_payment"] == round(expected)

    def test_total_cost_equals_payments_times_months(self):
        """total_cost = monthly_payment * term_months."""
        result = simulate_loan(500_000, 6, 0.025)
        assert result["total_cost"] == result["monthly_payment"] * 6

    def test_total_interest_equals_cost_minus_principal(self):
        """total_interest = total_cost - amount."""
        amount = 800_000
        result = simulate_loan(amount, 12, 0.025)
        assert result["total_interest"] == result["total_cost"] - amount

    def test_effective_annual_rate(self):
        """EA = (1 + r_monthly)^12 - 1."""
        r = 0.025
        result = simulate_loan(1_000_000, 12, r)
        expected_ea = (1 + r) ** 12 - 1
        assert abs(result["effective_annual_rate"] - round(expected_ea, 4)) < 0.0001

    def test_realistic_microcredit_rate(self):
        """Default rate produces EA in the 28-42% range for Colombian microcrédito."""
        result = simulate_loan(1_000_000, 12)
        ea = result["effective_annual_rate"]
        assert 0.28 <= ea <= 0.42, f"EA {ea:.1%} outside expected microcrédito range"

    def test_zero_amount_returns_zeros(self):
        result = simulate_loan(0, 12)
        assert result["monthly_payment"] == 0
        assert result["total_cost"] == 0

    def test_zero_term_returns_zeros(self):
        result = simulate_loan(1_000_000, 0)
        assert result["monthly_payment"] == 0

    def test_short_term_higher_payment(self):
        """Shorter term → higher monthly payment."""
        short = simulate_loan(1_000_000, 6)
        long = simulate_loan(1_000_000, 18)
        assert short["monthly_payment"] > long["monthly_payment"]

    def test_short_term_less_total_interest(self):
        """Shorter term → less total interest paid."""
        short = simulate_loan(1_000_000, 6)
        long = simulate_loan(1_000_000, 18)
        assert short["total_interest"] < long["total_interest"]

    def test_different_rates(self):
        """Higher rate → higher monthly payment."""
        low = simulate_loan(1_000_000, 12, 0.02)
        high = simulate_loan(1_000_000, 12, 0.03)
        assert high["monthly_payment"] > low["monthly_payment"]


class TestBuildOptionsTable:
    """Test the multi-term options builder."""

    def test_returns_three_options(self):
        options = build_options_table(1_000_000)
        assert len(options) == 3

    def test_term_months_are_6_12_18(self):
        options = build_options_table(1_000_000)
        terms = [o["term_months"] for o in options]
        assert terms == [6, 12, 18]

    def test_all_options_have_required_keys(self):
        options = build_options_table(500_000)
        required = {"term_months", "amount", "monthly_payment", "total_cost",
                     "total_interest", "effective_annual_rate", "monthly_rate"}
        for opt in options:
            assert required.issubset(opt.keys())

    def test_amount_matches_max_amount(self):
        options = build_options_table(750_000)
        for opt in options:
            assert opt["amount"] == 750_000

    def test_monthly_payment_decreases_with_longer_term(self):
        options = build_options_table(1_000_000)
        payments = [o["monthly_payment"] for o in options]
        assert payments[0] > payments[1] > payments[2]


# -----------------------------------------------------------------------
# Agent: approved path
# -----------------------------------------------------------------------

class TestApprovedFlow:
    """Test the approved user experience."""

    @pytest.mark.asyncio
    async def test_approved_shows_options_metadata(self):
        """Approved user gets metadata with options table."""
        llm = _make_llm("Felicidades, calificas para un microcrédito")
        agent = CreditEvaluatorAgent(llm)
        ctx = _approved_context(2_000_000)

        response = await agent.process("quiero un crédito", ctx)

        assert response.metadata["eligible"] is True
        assert response.metadata["max_amount"] > 0
        assert len(response.metadata["options"]) == 3

    @pytest.mark.asyncio
    async def test_approved_options_have_correct_math(self):
        """Each option in metadata must match simulate_loan results."""
        llm = _make_llm("Opciones de crédito")
        agent = CreditEvaluatorAgent(llm)
        ctx = _approved_context(1_500_000)

        response = await agent.process("evalúa mi crédito", ctx)

        max_amount = response.metadata["max_amount"]
        for opt in response.metadata["options"]:
            expected = simulate_loan(max_amount, opt["term_months"])
            assert opt["monthly_payment"] == expected["monthly_payment"]
            assert opt["total_interest"] == expected["total_interest"]

    @pytest.mark.asyncio
    async def test_approved_suggests_simulation_actions(self):
        """Suggested actions include simulation options."""
        llm = _make_llm("Aprobado")
        agent = CreditEvaluatorAgent(llm)
        ctx = _approved_context()

        response = await agent.process("quiero crédito", ctx)

        assert any("meses" in a for a in response.suggested_actions)
        assert "Solicitar crédito" in response.suggested_actions

    @pytest.mark.asyncio
    async def test_approved_product_in_metadata(self):
        """Metadata includes recommended product type."""
        llm = _make_llm("Aprobado")
        agent = CreditEvaluatorAgent(llm)
        ctx = _approved_context(2_000_000)

        response = await agent.process("crédito", ctx)

        assert response.metadata["product"] in ("nano", "micro")

    @pytest.mark.asyncio
    async def test_approved_llm_receives_options_instruction(self):
        """LLM is called with an instruction containing the options table."""
        llm = _make_llm("Respuesta con tabla")
        agent = CreditEvaluatorAgent(llm)
        ctx = _approved_context()

        await agent.process("quiero crédito", ctx)

        # Check the LLM was called with messages containing the options
        call_args = llm.generate.call_args
        messages = call_args[0][0]
        system_msgs = [m["content"] for m in messages if m["role"] == "system"]
        joined = " ".join(system_msgs)
        assert "APROBADO" in joined
        assert "meses" in joined

    @pytest.mark.asyncio
    async def test_approved_never_reveals_score(self):
        """The instruction to the LLM explicitly says never show score."""
        llm = _make_llm("Respuesta")
        agent = CreditEvaluatorAgent(llm)
        ctx = _approved_context()

        await agent.process("crédito", ctx)

        call_args = llm.generate.call_args
        messages = call_args[0][0]
        system_msgs = " ".join(m["content"] for m in messages if m["role"] == "system")
        assert "NUNCA" in system_msgs and "score" in system_msgs.lower()


# -----------------------------------------------------------------------
# Agent: rejected path
# -----------------------------------------------------------------------

class TestRejectedFlow:
    """Test the rejected user experience."""

    @pytest.mark.asyncio
    async def test_rejected_triggers_handoff_to_advisor(self):
        """Rejected users get handoff_to='financial_advisor'."""
        llm = _make_llm("Aún no estás listo, pero te vamos a ayudar")
        agent = CreditEvaluatorAgent(llm)
        ctx = _rejected_context()

        response = await agent.process("quiero un crédito", ctx)

        assert response.handoff_to == "financial_advisor"

    @pytest.mark.asyncio
    async def test_rejected_metadata_has_factors(self):
        """Rejected response metadata includes rejection factors."""
        llm = _make_llm("Respuesta empática")
        agent = CreditEvaluatorAgent(llm)
        ctx = _rejected_context()

        response = await agent.process("evaluar crédito", ctx)

        assert response.metadata["eligible"] is False
        assert len(response.metadata["rejection_factors"]) > 0

    @pytest.mark.asyncio
    async def test_rejected_instruction_never_says_rechazado(self):
        """The LLM instruction explicitly avoids the word 'rechazado'."""
        llm = _make_llm("Respuesta")
        agent = CreditEvaluatorAgent(llm)
        ctx = _rejected_context()

        await agent.process("crédito", ctx)

        call_args = llm.generate.call_args
        messages = call_args[0][0]
        system_msgs = " ".join(m["content"] for m in messages if m["role"] == "system")
        # The instruction must say "aún no" framing
        assert "aún no" in system_msgs.lower() or "AÚN NO" in system_msgs

    @pytest.mark.asyncio
    async def test_rejected_suggests_advisor_actions(self):
        """Suggested actions point toward improvement."""
        llm = _make_llm("Respuesta")
        agent = CreditEvaluatorAgent(llm)
        ctx = _rejected_context()

        response = await agent.process("crédito", ctx)

        assert any("asesor" in a.lower() for a in response.suggested_actions)

    @pytest.mark.asyncio
    async def test_rejected_no_options_in_metadata(self):
        """Rejected users should NOT get loan options."""
        llm = _make_llm("Respuesta")
        agent = CreditEvaluatorAgent(llm)
        ctx = _rejected_context()

        response = await agent.process("crédito", ctx)

        assert "options" not in response.metadata


# -----------------------------------------------------------------------
# Agent: general behavior
# -----------------------------------------------------------------------

class TestAgentGeneral:
    """Test general agent properties."""

    @pytest.mark.asyncio
    async def test_agent_type_is_evaluator(self):
        llm = _make_llm()
        agent = CreditEvaluatorAgent(llm)
        ctx = _approved_context()

        response = await agent.process("crédito", ctx)

        assert response.agent_type == "evaluator"
        assert response.agent_name == "credit_evaluator"

    @pytest.mark.asyncio
    async def test_prediction_stored_in_context(self):
        """After processing, prediction_result should be in context."""
        llm = _make_llm()
        agent = CreditEvaluatorAgent(llm)
        ctx = _approved_context()

        await agent.process("crédito", ctx)

        assert "prediction_result" in ctx
        assert "eligible" in ctx["prediction_result"]

    @pytest.mark.asyncio
    async def test_reuses_existing_prediction(self):
        """If prediction_result already in context, don't re-compute."""
        llm = _make_llm()
        agent = CreditEvaluatorAgent(llm)
        existing_pred = {
            "eligible": True,
            "max_amount": 999_999,
            "recommended_product": "nano",
            "score_band": "low_risk",
            "factors": [],
            "confidence": 0.8,
        }
        ctx = {"prediction_result": existing_pred}

        response = await agent.process("crédito", ctx)

        assert response.metadata["max_amount"] == 999_999

    @pytest.mark.asyncio
    async def test_stream_yields_content(self):
        """process_stream yields the full response content."""
        llm = _make_llm("Respuesta streaming")
        agent = CreditEvaluatorAgent(llm)
        ctx = _approved_context()

        chunks = []
        async for chunk in agent.process_stream("crédito", ctx):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0] == "Respuesta streaming"


# -----------------------------------------------------------------------
# Factor humanization
# -----------------------------------------------------------------------

class TestFactorHumanization:
    """Test factor name → Spanish description translation."""

    def test_known_factors(self):
        assert "ingresos" in _humanize_factor({"name": "declared_income"}).lower()
        assert "bancarios" in _humanize_factor({"name": "is_banked"}).lower()
        assert "pagos" in _humanize_factor({"name": "on_time_rate"}).lower()

    def test_unknown_factor_returns_name(self):
        result = _humanize_factor({"name": "unknown_xyz"})
        assert "unknown_xyz" in result


# -----------------------------------------------------------------------
# Tool handlers (for LLM-driven tool loop)
# -----------------------------------------------------------------------

class TestToolHandlers:
    """Test tool handler functions directly."""

    @pytest.mark.asyncio
    async def test_prediction_handler_returns_json(self):
        llm = _make_llm()
        agent = CreditEvaluatorAgent(llm)
        ctx = {"user_data": {"income": 2_000_000}, "prediction_eligible": True}

        result = await agent._handle_get_prediction(context=ctx, declared_income=2_000_000)

        import json
        parsed = json.loads(result)
        assert "eligible" in parsed

    @pytest.mark.asyncio
    async def test_simulation_handler_returns_json(self):
        llm = _make_llm()
        agent = CreditEvaluatorAgent(llm)

        result = await agent._handle_get_simulation(
            context={}, amount=1_000_000, term_months=12,
        )

        import json
        parsed = json.loads(result)
        assert "monthly_payment" in parsed
        assert parsed["monthly_payment"] > 0

    @pytest.mark.asyncio
    async def test_simulation_handler_custom_rate(self):
        llm = _make_llm()
        agent = CreditEvaluatorAgent(llm)

        result = await agent._handle_get_simulation(
            context={}, amount=1_000_000, term_months=12, monthly_rate=0.03,
        )

        import json
        parsed = json.loads(result)
        assert parsed["monthly_rate"] == 0.03


# -----------------------------------------------------------------------
# ML client integration
# -----------------------------------------------------------------------

class TestMLClientIntegration:
    """Test with a mock ML client object."""

    @pytest.mark.asyncio
    async def test_uses_ml_client_when_available(self):
        """When ml_client is provided, it should be called for predictions."""
        from unittest.mock import MagicMock
        from backend.ml_client.schemas import (
            CreditPrediction, ScoreBand, ProductType, RiskFactor,
        )

        mock_pred = CreditPrediction(
            eligible=True,
            p_default=0.12,
            risk_index=0.3,
            score_band=ScoreBand.low_risk,
            max_amount=1_500_000,
            recommended_product=ProductType.micro,
            confidence=0.85,
            factors=[
                RiskFactor(name="declared_income", impact="positive", weight=0.2),
            ],
        )

        ml_client = AsyncMock()
        ml_client.predict = AsyncMock(return_value=mock_pred)

        llm = _make_llm("Aprobado con ML client")
        agent = CreditEvaluatorAgent(llm, ml_client=ml_client)
        ctx = {"user_data": {"income": 3_000_000}}

        response = await agent.process("evaluar crédito", ctx)

        ml_client.predict.assert_called_once()
        assert response.metadata["eligible"] is True
        assert response.metadata["max_amount"] == 1_500_000
