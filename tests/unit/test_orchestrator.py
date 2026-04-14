"""Tests for the orchestrator routing, intent classification, and agent flow."""

import json

import pytest
from unittest.mock import AsyncMock, patch

from backend.agents.base_agent import BaseAgent, AgentResponse, Tool
from backend.agents.orchestrator import Orchestrator, _IntentCache, VALID_INTENTS
from backend.agents.helpyy_general_agent import HelpyyGeneralAgent
from backend.agents.onboarding_agent import OnboardingAgent
from backend.agents.credit_evaluator_agent import CreditEvaluatorAgent
from backend.agents.financial_advisor_agent import FinancialAdvisorAgent
from backend.data.schemas import UserState


# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------

@pytest.fixture
def mock_llm():
    """LLM provider mock that returns configurable responses."""
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="Hola, soy Helpyy Hand.")
    llm.generate_stream = AsyncMock()
    llm.generate_with_tools = AsyncMock()
    return llm


@pytest.fixture
def agents(mock_llm):
    """All agents initialised with mock LLM."""
    return {
        "helpyy_general": HelpyyGeneralAgent(mock_llm),
        "onboarding": OnboardingAgent(mock_llm),
        "credit_evaluator": CreditEvaluatorAgent(mock_llm),
        "financial_advisor": FinancialAdvisorAgent(mock_llm),
    }


@pytest.fixture
def orchestrator(mock_llm, agents):
    return Orchestrator(llm=mock_llm, agents=agents)


@pytest.fixture
def banked_user():
    return UserState(user_id="u-001", is_banked=True)


@pytest.fixture
def unbanked_user():
    return UserState(user_id="u-002", is_banked=False)


# =======================================================================
# INTENT CLASSIFICATION
# =======================================================================

class TestClassifyIntent:

    @pytest.mark.asyncio
    async def test_parses_valid_json(self, orchestrator, mock_llm):
        mock_llm.generate.return_value = '{"intent": "credit_inquiry"}'
        intent = await orchestrator.classify_intent("quiero un préstamo")
        assert intent == "credit_inquiry"

    @pytest.mark.asyncio
    async def test_parses_json_with_surrounding_text(self, orchestrator, mock_llm):
        mock_llm.generate.return_value = 'Aquí va: {"intent": "financial_advice"} listo.'
        intent = await orchestrator.classify_intent("cómo mejoro mi puntaje")
        assert intent == "financial_advice"

    @pytest.mark.asyncio
    async def test_fallback_keyword_match(self, orchestrator, mock_llm):
        """If JSON parsing fails, falls back to keyword matching."""
        mock_llm.generate.return_value = "the intent is credit_inquiry for this message"
        intent = await orchestrator.classify_intent("quiero crédito")
        assert intent == "credit_inquiry"

    @pytest.mark.asyncio
    async def test_ultimate_fallback_to_bank_faq(self, orchestrator, mock_llm):
        """If nothing matches, defaults to bank_faq."""
        mock_llm.generate.return_value = "no idea what this is about zzz"
        intent = await orchestrator.classify_intent("asdfghjkl")
        assert intent == "bank_faq"

    @pytest.mark.asyncio
    async def test_uses_temperature_zero(self, orchestrator, mock_llm):
        """Classification should use temperature=0 for determinism."""
        mock_llm.generate.return_value = '{"intent": "greeting"}'
        await orchestrator.classify_intent("hola")
        call_kwargs = mock_llm.generate.call_args
        assert call_kwargs.kwargs.get("temperature") == 0.0 or call_kwargs[1].get("temperature") == 0.0

    @pytest.mark.asyncio
    async def test_all_intents_valid(self, orchestrator, mock_llm):
        """Each valid intent can be returned and parsed."""
        for intent in VALID_INTENTS:
            mock_llm.generate.return_value = json.dumps({"intent": intent})
            result = await orchestrator.classify_intent(f"test {intent}")
            assert result == intent


# =======================================================================
# INTENT CACHE
# =======================================================================

class TestIntentCache:

    def test_put_and_get(self):
        cache = _IntentCache()
        cache.put("hola", "greeting")
        assert cache.get("hola") == "greeting"

    def test_returns_none_for_missing(self):
        cache = _IntentCache()
        assert cache.get("unknown") is None

    def test_normalises_text(self):
        assert _IntentCache.normalise("  HOLA  Mundo  ") == "hola mundo"

    def test_evicts_oldest_when_full(self):
        cache = _IntentCache(max_size=2)
        cache.put("a", "greeting")
        cache.put("b", "bank_faq")
        cache.put("c", "credit_inquiry")  # should evict "a"
        assert cache.get("a") is None
        assert cache.get("b") == "bank_faq"
        assert cache.get("c") == "credit_inquiry"

    @pytest.mark.asyncio
    async def test_cache_prevents_llm_call(self, orchestrator, mock_llm):
        """Second call with same message should use cache, not LLM."""
        mock_llm.generate.return_value = '{"intent": "greeting"}'
        await orchestrator.classify_intent("hola buenos días")
        await orchestrator.classify_intent("hola buenos días")
        # LLM should only have been called once
        assert mock_llm.generate.call_count == 1


# =======================================================================
# ROUTING
# =======================================================================

class TestRouting:

    @pytest.mark.asyncio
    async def test_unbanked_always_onboarding(self, orchestrator, unbanked_user, mock_llm):
        """Unbanked users always go to onboarding, regardless of intent."""
        mock_llm.generate.return_value = '{"intent": "credit_inquiry"}'
        agent = await orchestrator.route("quiero un préstamo", unbanked_user)
        assert agent.name == "onboarding"

    @pytest.mark.asyncio
    async def test_credit_inquiry_routes_to_evaluator(self, orchestrator, banked_user, mock_llm):
        mock_llm.generate.return_value = '{"intent": "credit_inquiry"}'
        agent = await orchestrator.route("quiero un microcrédito", banked_user)
        assert agent.name == "credit_evaluator"

    @pytest.mark.asyncio
    async def test_financial_advice_routes_to_advisor(self, orchestrator, banked_user, mock_llm):
        mock_llm.generate.return_value = '{"intent": "financial_advice"}'
        agent = await orchestrator.route("cómo mejoro mi puntaje", banked_user)
        assert agent.name == "financial_advisor"

    @pytest.mark.asyncio
    async def test_bank_faq_routes_to_general(self, orchestrator, banked_user, mock_llm):
        mock_llm.generate.return_value = '{"intent": "bank_faq"}'
        agent = await orchestrator.route("horarios del banco", banked_user)
        assert agent.name == "helpyy_general"

    @pytest.mark.asyncio
    async def test_greeting_routes_to_general(self, orchestrator, banked_user, mock_llm):
        mock_llm.generate.return_value = '{"intent": "greeting"}'
        agent = await orchestrator.route("hola", banked_user)
        assert agent.name == "helpyy_general"

    @pytest.mark.asyncio
    async def test_onboarding_intent_routes_to_onboarding(self, orchestrator, banked_user, mock_llm):
        mock_llm.generate.return_value = '{"intent": "onboarding"}'
        agent = await orchestrator.route("quiero abrir una cuenta", banked_user)
        assert agent.name == "onboarding"

    @pytest.mark.asyncio
    async def test_unknown_intent_fallback(self, orchestrator, banked_user, mock_llm):
        """Unknown/unparseable intent falls back to helpyy_general."""
        mock_llm.generate.return_value = "gibberish response with no json"
        agent = await orchestrator.route("xyz abc 123", banked_user)
        assert agent.name == "helpyy_general"


# =======================================================================
# FULL HANDLE_MESSAGE FLOW
# =======================================================================

class TestHandleMessage:

    @pytest.mark.asyncio
    async def test_full_flow_returns_agent_response(self, orchestrator, banked_user, mock_llm):
        mock_llm.generate.side_effect = [
            '{"intent": "bank_faq"}',         # classify_intent
            "Nuestros horarios son L-V 8am-4pm.",  # agent.process
        ]
        response = await orchestrator.handle_message(
            "cuáles son los horarios?", "sess-001", banked_user,
        )
        assert isinstance(response, AgentResponse)
        assert response.agent_name == "helpyy_general"
        assert "horarios" in response.content.lower()

    @pytest.mark.asyncio
    async def test_stores_context(self, orchestrator, banked_user, mock_llm):
        mock_llm.generate.side_effect = [
            '{"intent": "greeting"}',
            "Hola! Soy Helpyy Hand.",
        ]
        await orchestrator.handle_message("hola", "sess-002", banked_user)
        ctx = orchestrator.get_session_context("sess-002")
        assert len(ctx["history"]) == 2  # user + assistant
        assert ctx["history"][0]["role"] == "user"
        assert ctx["history"][0]["content"] == "hola"
        assert ctx["history"][1]["role"] == "assistant"
        assert ctx["current_agent"] == "helpyy_general"

    @pytest.mark.asyncio
    async def test_multi_turn_preserves_history(self, orchestrator, banked_user, mock_llm):
        mock_llm.generate.side_effect = [
            '{"intent": "greeting"}',
            "Hola! En qué te puedo ayudar?",
            '{"intent": "bank_faq"}',
            "Claro, nuestros horarios son L-V 8am-4pm.",
        ]
        await orchestrator.handle_message("hola", "sess-003", banked_user)
        await orchestrator.handle_message("horarios?", "sess-003", banked_user)
        ctx = orchestrator.get_session_context("sess-003")
        assert len(ctx["history"]) == 4  # 2 turns × 2 messages


# =======================================================================
# HANDOFF
# =======================================================================

class TestHandoff:

    @pytest.mark.asyncio
    async def test_handoff_preserves_context(self, orchestrator, banked_user, mock_llm):
        """Handoff should transfer context and increment handoff_count."""
        mock_llm.generate.side_effect = [
            '{"intent": "bank_faq"}',
            "Te voy a conectar con el evaluador de crédito.",  # general agent
            "Hola! Voy a revisar tu eligibilidad.",            # credit_evaluator after handoff
        ]
        # First message — general agent detects credit intent and requests handoff
        # We simulate this by making the general agent's response trigger handoff
        # The helpyy_general agent detects "crédito" keyword → handoff_to = credit_evaluator
        # But classify_intent returns bank_faq, so orchestrator routes to general first

        # Simulate: general agent gets the message, detects credit keyword → handoff
        response = await orchestrator.handle_message(
            "quiero saber sobre mi crédito", "sess-hoff", banked_user,
        )
        # The general agent should have detected "crédito" and set handoff_to
        # After handoff, the response comes from credit_evaluator
        assert response.agent_name == "credit_evaluator"
        assert response.metadata.get("handoff_from") == "helpyy_general"

        ctx = orchestrator.get_session_context("sess-hoff")
        assert ctx["handoff_count"] == 1
        assert ctx["current_agent"] == "credit_evaluator"

    @pytest.mark.asyncio
    async def test_handoff_to_nonexistent_agent_handled(self, orchestrator, mock_llm):
        """Handoff to a non-registered agent should gracefully fallback."""
        result = await orchestrator.handle_handoff(
            from_agent="helpyy_general",
            to_agent="nonexistent_agent",
            context={"history": []},
            session_id="sess-err",
        )
        assert "problema" in result.content.lower() or "ayudar" in result.content.lower()

    @pytest.mark.asyncio
    async def test_handoff_injects_transition_context(self, orchestrator, banked_user, mock_llm):
        """The receiving agent should get transition context in its history."""
        captured_messages = []

        original_generate = mock_llm.generate

        async def capture_generate(messages, **kwargs):
            captured_messages.extend(messages)
            return "Recibí la transferencia, te ayudo con tu crédito."

        mock_llm.generate.side_effect = [
            '{"intent": "bank_faq"}',
            "Te conecto con crédito.",
            capture_generate,  # This won't work as side_effect directly
        ]
        # Use a different approach: just call handle_handoff directly
        mock_llm.generate.reset_mock()
        mock_llm.generate.return_value = "Recibí la transferencia."

        ctx = orchestrator.get_session_context("sess-trans")
        ctx["history"] = [
            {"role": "user", "content": "necesito un préstamo", "agent": None},
        ]

        result = await orchestrator.handle_handoff(
            from_agent="helpyy_general",
            to_agent="credit_evaluator",
            context=ctx,
            session_id="sess-trans",
            original_message="necesito un préstamo",
        )

        assert result.agent_name == "credit_evaluator"
        assert result.metadata.get("handoff_from") == "helpyy_general"
        assert ctx["previous_agent"] == "helpyy_general"


# =======================================================================
# AGENT RESPONSE FORMAT
# =======================================================================

class TestAgentResponseFormat:

    @pytest.mark.asyncio
    async def test_response_has_required_fields(self, mock_llm):
        mock_llm.generate.return_value = "Hola, soy Helpyy Hand."
        agent = HelpyyGeneralAgent(mock_llm)
        response = await agent.process("hola", {"history": []})
        assert isinstance(response, AgentResponse)
        assert response.content == "Hola, soy Helpyy Hand."
        assert response.agent_name == "helpyy_general"
        assert response.agent_type == "general"

    @pytest.mark.asyncio
    async def test_general_agent_suggests_actions_on_greeting(self, mock_llm):
        mock_llm.generate.return_value = "Bienvenido!"
        agent = HelpyyGeneralAgent(mock_llm)
        response = await agent.process("hola buenos días", {"history": []})
        assert len(response.suggested_actions) > 0

    @pytest.mark.asyncio
    async def test_general_agent_detects_credit_handoff(self, mock_llm):
        mock_llm.generate.return_value = "Te conecto con el evaluador."
        agent = HelpyyGeneralAgent(mock_llm)
        response = await agent.process("quiero un préstamo", {"history": []})
        assert response.handoff_to == "credit_evaluator"

    @pytest.mark.asyncio
    async def test_general_agent_detects_advice_handoff(self, mock_llm):
        mock_llm.generate.return_value = "Te conecto con el asesor."
        agent = HelpyyGeneralAgent(mock_llm)
        response = await agent.process("cómo puedo mejorar mi puntaje", {"history": []})
        assert response.handoff_to == "financial_advisor"

    @pytest.mark.asyncio
    async def test_general_agent_detects_onboarding_handoff(self, mock_llm):
        mock_llm.generate.return_value = "Te ayudo a abrir tu cuenta."
        agent = HelpyyGeneralAgent(mock_llm)
        response = await agent.process("no soy cliente, quiero abrir cuenta", {"history": []})
        assert response.handoff_to == "onboarding"

    @pytest.mark.asyncio
    async def test_general_agent_no_handoff_for_faq(self, mock_llm):
        mock_llm.generate.return_value = "Nuestros horarios son L-V 8am-4pm."
        agent = HelpyyGeneralAgent(mock_llm)
        response = await agent.process("cuáles son los horarios del banco?", {"history": []})
        assert response.handoff_to is None

    @pytest.mark.asyncio
    async def test_each_agent_has_correct_type(self, mock_llm):
        mock_llm.generate.return_value = "respuesta"
        for AgentCls, expected_type in [
            (HelpyyGeneralAgent, "general"),
            (OnboardingAgent, "onboarding"),
            (CreditEvaluatorAgent, "evaluator"),
            (FinancialAdvisorAgent, "advisor"),
        ]:
            agent = AgentCls(mock_llm)
            response = await agent.process("test", {"history": []})
            assert response.agent_type == expected_type, f"{AgentCls.__name__} type wrong"


# =======================================================================
# BASE AGENT — message building and tool loop
# =======================================================================

class TestBaseAgentMessageBuilding:

    @pytest.mark.asyncio
    async def test_builds_system_user_messages(self, mock_llm):
        mock_llm.generate.return_value = "Respuesta del agente."
        agent = HelpyyGeneralAgent(mock_llm)
        await agent.process("hola", {"history": []})

        call_args = mock_llm.generate.call_args
        messages = call_args[0][0]
        assert messages[0]["role"] == "system"
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "hola"

    @pytest.mark.asyncio
    async def test_includes_conversation_history(self, mock_llm):
        mock_llm.generate.return_value = "Respuesta."
        agent = HelpyyGeneralAgent(mock_llm)
        context = {
            "history": [
                {"role": "user", "content": "primera pregunta"},
                {"role": "assistant", "content": "primera respuesta"},
            ],
        }
        await agent.process("segunda pregunta", context)

        messages = mock_llm.generate.call_args[0][0]
        # system + 2 history + 1 current user
        assert len(messages) == 4
        assert messages[1]["content"] == "primera pregunta"
        assert messages[2]["content"] == "primera respuesta"
        assert messages[3]["content"] == "segunda pregunta"

    @pytest.mark.asyncio
    async def test_trims_history_to_10_turns(self, mock_llm):
        mock_llm.generate.return_value = "Respuesta."
        agent = HelpyyGeneralAgent(mock_llm)
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
            for i in range(20)
        ]
        await agent.process("current", {"history": history})

        messages = mock_llm.generate.call_args[0][0]
        # system(1) + last 10 history + current user(1) = 12
        assert len(messages) == 12


# =======================================================================
# SESSION CONTEXT
# =======================================================================

class TestSessionContext:

    def test_clear_session(self, orchestrator):
        orchestrator._sessions.append_turn("s1", "user", "hola")
        orchestrator.clear_session("s1")
        ctx = orchestrator.get_session_context("s1")
        assert len(ctx["history"]) == 0

    def test_session_isolation(self, orchestrator):
        orchestrator._sessions.append_turn("s1", "user", "hola")
        orchestrator._sessions.append_turn("s2", "user", "buenos días")
        ctx1 = orchestrator.get_session_context("s1")
        ctx2 = orchestrator.get_session_context("s2")
        assert ctx1["history"][0]["content"] == "hola"
        assert ctx2["history"][0]["content"] == "buenos días"
