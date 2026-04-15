"""Tests for the financial advisor agent — gamification, missions, plans.

Covers: plan creation based on ML factors, mission personalization by occupation,
points/levels calculation, mission completion, progress tracking, intent routing.
"""

from unittest.mock import AsyncMock

import pytest

from backend.agents.financial_advisor_agent import (
    FinancialAdvisorAgent,
    MISSION_CATALOG,
    build_plan,
    calculate_plan_points,
    compute_level,
    _detect_advisor_intent,
    _get_occupation_tip,
    _instantiate_mission,
)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _make_llm(response: str = "respuesta del asesor") -> AsyncMock:
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value=response)
    llm.generate_stream = AsyncMock()
    return llm


def _factors_for_low_income_unbanked() -> list[dict]:
    """Typical factors for a low-income unbanked user (worst case)."""
    return [
        {"factor_name": "on_time_rate", "current_value": 0.0, "target_value": 0.9,
         "potential_reduction": 0.12, "suggestion": "Paga tus cuotas a tiempo."},
        {"factor_name": "overdue_rate", "current_value": 0.3, "target_value": 0.05,
         "potential_reduction": 0.08, "suggestion": "Evita atrasos."},
        {"factor_name": "pct_conversion", "current_value": 0.1, "target_value": 0.6,
         "potential_reduction": 0.04, "suggestion": "Usa la app."},
        {"factor_name": "is_banked", "current_value": 0.0, "target_value": 1.0,
         "potential_reduction": 0.02, "suggestion": "Abre una cuenta."},
    ]


def _factors_on_time_only() -> list[dict]:
    """Only on_time_rate needs improvement."""
    return [
        {"factor_name": "on_time_rate", "current_value": 0.5, "target_value": 0.9,
         "potential_reduction": 0.10, "suggestion": "Paga a tiempo."},
    ]


# -----------------------------------------------------------------------
# Level system
# -----------------------------------------------------------------------

class TestComputeLevel:
    """Test the points → level mapping."""

    def test_zero_points_is_principiante(self):
        result = compute_level(0)
        assert result["level"] == 1
        assert result["level_name"] == "Principiante"
        assert result["next_level_at"] == 50

    def test_50_points_is_aprendiz(self):
        result = compute_level(50)
        assert result["level_name"] == "Aprendiz"
        assert result["level"] == 2

    def test_150_points_is_disciplinado(self):
        result = compute_level(150)
        assert result["level_name"] == "Disciplinado"

    def test_300_points_is_experto(self):
        result = compute_level(300)
        assert result["level_name"] == "Experto"

    def test_500_points_is_maestro(self):
        result = compute_level(500)
        assert result["level_name"] == "Maestro Financiero"
        assert result["points_to_next"] == 0  # max level

    def test_intermediate_points(self):
        """75 points → Aprendiz, needs 75 more for Disciplinado."""
        result = compute_level(75)
        assert result["level_name"] == "Aprendiz"
        assert result["points_to_next"] == 150 - 75

    def test_level_increases_monotonically(self):
        levels = [compute_level(p)["level"] for p in [0, 50, 150, 300, 500]]
        assert levels == [1, 2, 3, 4, 5]


# -----------------------------------------------------------------------
# Plan building
# -----------------------------------------------------------------------

class TestBuildPlan:
    """Test plan creation from ML improvement factors."""

    def test_advisor_creates_personalized_plan(self):
        """Plan targets the user's specific weak ML factors."""
        factors = _factors_for_low_income_unbanked()
        plan = build_plan(factors, occupation="vendedor_ambulante")

        assert len(plan) >= 3
        # All missions should target factors the user needs to improve
        targeted_factors = {m["factor"] for m in plan}
        user_factor_names = {f["factor_name"] for f in factors}
        assert targeted_factors.issubset(user_factor_names)

    def test_missions_are_based_on_ml_factors(self):
        """Missions only include factors from the ML improvement list."""
        # Only on_time_rate needs improvement
        factors = _factors_on_time_only()
        plan = build_plan(factors)

        for mission in plan:
            assert mission["factor"] == "on_time_rate"

    def test_plan_respects_week_limit(self):
        """No mission starts after plan_weeks."""
        factors = _factors_for_low_income_unbanked()
        plan = build_plan(factors, plan_weeks=4)

        for mission in plan:
            assert mission["start_week"] <= 4

    def test_plan_minimum_4_weeks(self):
        """Plan enforces minimum 4 weeks."""
        factors = _factors_for_low_income_unbanked()
        plan = build_plan(factors, plan_weeks=1)  # too short

        # Should still have missions (plan_weeks clamped to 4)
        assert len(plan) > 0
        assert all(m["start_week"] <= 4 for m in plan)

    def test_plan_maximum_8_weeks(self):
        """Plan enforces maximum 8 weeks."""
        factors = _factors_for_low_income_unbanked()
        plan = build_plan(factors, plan_weeks=20)  # too long

        for mission in plan:
            assert mission["end_week"] <= 8

    def test_plan_ordered_by_difficulty(self):
        """Easy missions come before hard ones."""
        factors = _factors_for_low_income_unbanked()
        plan = build_plan(factors)

        difficulty_order = {"easy": 0, "medium": 1, "hard": 2}
        difficulties = [difficulty_order[m["difficulty"]] for m in plan]
        assert difficulties == sorted(difficulties)

    def test_plan_with_no_factors_gives_engagement_missions(self):
        """If user has no factors to improve, get engagement missions."""
        plan = build_plan([])
        assert len(plan) > 0
        # Should include pct_conversion or is_banked missions
        factors_in_plan = {m["factor"] for m in plan}
        assert factors_in_plan & {"pct_conversion", "is_banked"}

    def test_missions_have_required_fields(self):
        """Every mission has all required fields."""
        factors = _factors_for_low_income_unbanked()
        plan = build_plan(factors)

        required = {"mission_id", "factor", "points", "title", "description",
                     "criteria", "weeks", "difficulty", "status", "progress",
                     "start_week", "end_week"}
        for mission in plan:
            assert required.issubset(mission.keys()), f"Missing keys: {required - mission.keys()}"

    def test_missions_start_as_pending(self):
        factors = _factors_for_low_income_unbanked()
        plan = build_plan(factors)
        for m in plan:
            assert m["status"] == "pending"
            assert m["progress"] == 0.0


# -----------------------------------------------------------------------
# Occupation personalization
# -----------------------------------------------------------------------

class TestOccupationTips:
    """Test occupation-specific mission personalization."""

    def test_vendedor_gets_arepas_tip(self):
        tip = _get_occupation_tip("vendedor_ambulante", "deposit_constant")
        assert "arepas" in tip.lower() or "empanadas" in tip.lower()

    def test_domestico_gets_employer_tip(self):
        tip = _get_occupation_tip("trabajador_domestico", "deposit_constant")
        assert "empleador" in tip.lower()

    def test_independiente_gets_factura_tip(self):
        tip = _get_occupation_tip("independiente", "salary_registered")
        assert "factura" in tip.lower()

    def test_default_occupation_gets_generic_tip(self):
        tip = _get_occupation_tip("default", "deposit_constant")
        assert len(tip) > 0

    def test_unknown_occupation_uses_default(self):
        tip = _get_occupation_tip("astronauta", "deposit_constant")
        # Should fall back to default tips
        assert len(tip) > 0

    def test_plan_includes_occupation_tips(self):
        """Mission descriptions include occupation-specific text."""
        factors = _factors_for_low_income_unbanked()
        plan = build_plan(factors, occupation="vendedor_ambulante")

        # At least one mission should have vendor-specific tip
        descriptions = " ".join(m["description"] for m in plan)
        assert "arepas" in descriptions.lower() or "empanadas" in descriptions.lower() or \
               "venta" in descriptions.lower() or "vendedor" in descriptions.lower()


# -----------------------------------------------------------------------
# Gamification points
# -----------------------------------------------------------------------

class TestGamificationPoints:
    """Test points calculation for plans."""

    def test_gamification_points_calculation(self):
        """Points earned matches sum of completed mission points."""
        missions = [
            {"points": 15, "status": "completed"},
            {"points": 25, "status": "completed"},
            {"points": 30, "status": "pending"},
        ]
        result = calculate_plan_points(missions)
        assert result["earned"] == 40
        assert result["total_possible"] == 70
        assert result["completion_pct"] == pytest.approx(57.1, abs=0.1)

    def test_no_missions_returns_zero(self):
        result = calculate_plan_points([])
        assert result["earned"] == 0
        assert result["total_possible"] == 0
        assert result["completion_pct"] == 0

    def test_all_completed(self):
        missions = [
            {"points": 10, "status": "completed"},
            {"points": 20, "status": "completed"},
        ]
        result = calculate_plan_points(missions)
        assert result["completion_pct"] == 100.0

    def test_none_completed(self):
        missions = [
            {"points": 15, "status": "pending"},
            {"points": 25, "status": "in_progress"},
        ]
        result = calculate_plan_points(missions)
        assert result["earned"] == 0
        assert result["completion_pct"] == 0

    def test_catalog_missions_have_positive_points(self):
        """Every mission in the catalog awards at least 1 point."""
        for m in MISSION_CATALOG:
            assert m["points"] > 0, f"{m['id_prefix']} has {m['points']} points"


# -----------------------------------------------------------------------
# Mission instantiation
# -----------------------------------------------------------------------

class TestMissionInstantiation:
    """Test creating concrete missions from catalog templates."""

    def test_instantiate_generates_unique_id(self):
        template = MISSION_CATALOG[0]
        m1 = _instantiate_mission(template, "default")
        m2 = _instantiate_mission(template, "default")
        assert m1["mission_id"] != m2["mission_id"]

    def test_instantiate_preserves_points(self):
        template = MISSION_CATALOG[0]
        mission = _instantiate_mission(template, "default")
        assert mission["points"] == template["points"]

    def test_instantiate_sets_pending_status(self):
        template = MISSION_CATALOG[0]
        mission = _instantiate_mission(template, "default")
        assert mission["status"] == "pending"
        assert mission["progress"] == 0.0


# -----------------------------------------------------------------------
# Intent detection
# -----------------------------------------------------------------------

class TestIntentDetection:
    def test_plan_keywords(self):
        assert _detect_advisor_intent("Quiero crear un plan") == "create_plan"
        assert _detect_advisor_intent("Dame misiones") == "create_plan"
        assert _detect_advisor_intent("Quiero mejorar mi score") == "create_plan"

    def test_progress_keywords(self):
        assert _detect_advisor_intent("Cómo voy?") == "check_progress"
        assert _detect_advisor_intent("Mi progreso") == "check_progress"
        assert _detect_advisor_intent("Cuál es mi nivel?") == "check_progress"

    def test_complete_keywords(self):
        assert _detect_advisor_intent("Ya completé la misión") == "complete_mission"
        assert _detect_advisor_intent("Terminé el reto") == "complete_mission"
        assert _detect_advisor_intent("Ya lo hice") == "complete_mission"

    def test_general_fallback(self):
        assert _detect_advisor_intent("Hola, necesito ayuda") == "general_advice"


# -----------------------------------------------------------------------
# Agent: create plan flow
# -----------------------------------------------------------------------

class TestAdvisorCreatePlan:
    """Test the full plan creation through the agent."""

    @pytest.mark.asyncio
    async def test_creates_plan_from_factors(self):
        """Agent creates a plan targeting the user's ML factors."""
        llm = _make_llm("Tu plan personalizado está listo")
        agent = FinancialAdvisorAgent(llm)
        ctx = {
            "improvement_factors": _factors_for_low_income_unbanked(),
            "user_data": {"occupation": "vendedor_ambulante"},
        }

        response = await agent.process("Quiero crear un plan", ctx)

        assert "plan" in response.metadata
        plan = response.metadata["plan"]
        assert len(plan) >= 3
        assert response.metadata["level"]["level_name"] == "Principiante"

    @pytest.mark.asyncio
    async def test_plan_metadata_has_points_info(self):
        llm = _make_llm("Plan creado")
        agent = FinancialAdvisorAgent(llm)
        ctx = {
            "improvement_factors": _factors_for_low_income_unbanked(),
            "user_data": {"occupation": "default"},
        }

        response = await agent.process("Crear plan de misiones", ctx)

        assert "points" in response.metadata
        assert response.metadata["points"]["total_possible"] > 0
        assert response.metadata["points"]["earned"] == 0

    @pytest.mark.asyncio
    async def test_plan_stored_in_context(self):
        llm = _make_llm("Plan listo")
        agent = FinancialAdvisorAgent(llm)
        ctx = {
            "improvement_factors": _factors_on_time_only(),
            "user_data": {},
        }

        await agent.process("Dame misiones", ctx)

        assert "plan" in ctx
        assert len(ctx["plan"]) > 0

    @pytest.mark.asyncio
    async def test_llm_receives_plan_instruction(self):
        """LLM gets an instruction with the plan details."""
        llm = _make_llm("Plan")
        agent = FinancialAdvisorAgent(llm)
        ctx = {
            "improvement_factors": _factors_for_low_income_unbanked(),
            "user_data": {"occupation": "independiente"},
        }

        await agent.process("Crear plan", ctx)

        call_args = llm.generate.call_args
        messages = call_args[0][0]
        system_msgs = " ".join(m["content"] for m in messages if m["role"] == "system")
        assert "misiones" in system_msgs.lower() or "Semana" in system_msgs


# -----------------------------------------------------------------------
# Agent: progress & completion
# -----------------------------------------------------------------------

class TestAdvisorProgress:
    @pytest.mark.asyncio
    async def test_check_progress_shows_status(self):
        llm = _make_llm("Vas muy bien")
        agent = FinancialAdvisorAgent(llm)
        ctx = {
            "plan": [
                {"title": "Deposita $50.000 esta semana", "points": 15, "status": "completed",
                 "progress": 1.0, "mission_id": "m1"},
                {"title": "Colchón de Seguridad", "points": 25, "status": "pending",
                 "progress": 0.0, "mission_id": "m2"},
            ],
            "total_points": 15,
        }

        response = await agent.process("Cómo voy?", ctx)

        assert response.metadata["completed_count"] == 1
        assert response.metadata["total_missions"] == 2

    @pytest.mark.asyncio
    async def test_complete_mission_awards_points(self):
        llm = _make_llm("Felicidades!")
        agent = FinancialAdvisorAgent(llm)
        ctx = {
            "plan": [
                {"title": "Test Mission", "points": 25, "status": "pending",
                 "progress": 0.0, "mission_id": "m1", "factor": "on_time_rate",
                 "difficulty": "easy"},
            ],
            "total_points": 0,
        }

        response = await agent.process("Ya completé la misión", ctx)

        assert ctx["total_points"] == 25
        assert response.metadata["points_earned"] == 25
        assert response.metadata["completed_mission"] == "Test Mission"

    @pytest.mark.asyncio
    async def test_complete_mission_updates_level(self):
        llm = _make_llm("Subiste de nivel!")
        agent = FinancialAdvisorAgent(llm)
        ctx = {
            "plan": [
                {"title": "Big Mission", "points": 50, "status": "pending",
                 "progress": 0.0, "mission_id": "m1", "factor": "on_time_rate",
                 "difficulty": "medium"},
            ],
            "total_points": 0,
        }

        response = await agent.process("Terminé", ctx)

        assert response.metadata["level"]["level_name"] == "Aprendiz"

    @pytest.mark.asyncio
    async def test_no_pending_missions_suggests_new_plan(self):
        llm = _make_llm("Todas las misiones completadas!")
        agent = FinancialAdvisorAgent(llm)
        ctx = {
            "plan": [
                {"title": "Done", "points": 10, "status": "completed",
                 "progress": 1.0, "mission_id": "m1"},
            ],
            "total_points": 10,
        }

        response = await agent.process("Completé otra", ctx)

        assert "nuevo plan" in " ".join(response.suggested_actions).lower() or \
               "Crear" in " ".join(response.suggested_actions)


# -----------------------------------------------------------------------
# Agent: general properties
# -----------------------------------------------------------------------

class TestAgentGeneral:
    @pytest.mark.asyncio
    async def test_agent_type_is_advisor(self):
        llm = _make_llm()
        agent = FinancialAdvisorAgent(llm)
        response = await agent.process("Hola", {})
        assert response.agent_type == "advisor"
        assert response.agent_name == "financial_advisor"

    @pytest.mark.asyncio
    async def test_stream_yields_content(self):
        llm = _make_llm("Streaming response")
        agent = FinancialAdvisorAgent(llm)
        chunks = []
        async for chunk in agent.process_stream("Hola", {}):
            chunks.append(chunk)
        assert chunks == ["Streaming response"]

    @pytest.mark.asyncio
    async def test_general_advice_suggests_plan(self):
        llm = _make_llm("Te recomiendo...")
        agent = FinancialAdvisorAgent(llm)
        response = await agent.process("Necesito ayuda financiera", {})
        assert any("plan" in a.lower() for a in response.suggested_actions)

    @pytest.mark.asyncio
    async def test_uses_rejection_factors_from_handoff(self):
        """When coming from credit evaluator handoff, uses rejection_factors."""
        llm = _make_llm("Plan basado en factores")
        agent = FinancialAdvisorAgent(llm)
        ctx = {
            "rejection_factors": ["on_time_rate", "overdue_rate"],
            "user_data": {},
        }

        await agent.process("Quiero mejorar", ctx)

        # Should have created a plan from rejection factors
        assert "plan" in ctx


# -----------------------------------------------------------------------
# Tool handlers
# -----------------------------------------------------------------------

class TestToolHandlers:
    @pytest.mark.asyncio
    async def test_get_profile_returns_json(self):
        llm = _make_llm()
        agent = FinancialAdvisorAgent(llm)
        ctx = {"user_data": {"income": 800_000, "occupation": "vendedor_ambulante"}}

        result = await agent._handle_get_profile(context=ctx)

        import json
        parsed = json.loads(result)
        assert parsed["income"] == 800_000

    @pytest.mark.asyncio
    async def test_get_factors_returns_json(self):
        llm = _make_llm()
        agent = FinancialAdvisorAgent(llm)
        ctx = {"improvement_factors": _factors_on_time_only()}

        result = await agent._handle_get_factors(context=ctx)

        import json
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["factor_name"] == "on_time_rate"

    @pytest.mark.asyncio
    async def test_create_mission_adds_to_plan(self):
        llm = _make_llm()
        agent = FinancialAdvisorAgent(llm)
        ctx = {"user_data": {"occupation": "default"}}

        result = await agent._handle_create_mission(
            context=ctx, mission_type="deposit_constant", user_id="u1",
        )

        import json
        parsed = json.loads(result)
        assert parsed["title"] == "Deposita $50.000 esta semana"
        assert len(ctx["plan"]) == 1

    @pytest.mark.asyncio
    async def test_update_progress_completes_mission(self):
        llm = _make_llm()
        agent = FinancialAdvisorAgent(llm)
        ctx = {
            "plan": [
                {"mission_id": "test_123", "title": "Test", "points": 20,
                 "status": "pending", "progress": 0.0},
            ],
            "total_points": 0,
        }

        result = await agent._handle_update_progress(
            context=ctx, mission_id="test_123", completed=True,
        )

        import json
        parsed = json.loads(result)
        assert parsed["status"] == "completed"
        assert ctx["total_points"] == 20

    @pytest.mark.asyncio
    async def test_update_progress_unknown_mission(self):
        llm = _make_llm()
        agent = FinancialAdvisorAgent(llm)
        ctx = {"plan": []}

        result = await agent._handle_update_progress(
            context=ctx, mission_id="nonexistent",
        )

        import json
        parsed = json.loads(result)
        assert parsed["error"] == "mission_not_found"
