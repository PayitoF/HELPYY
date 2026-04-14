"""Orchestrator — routes messages to the correct agent based on intent and user state.

Uses the LLM with a lightweight classification prompt to determine intent,
then dispatches to the appropriate agent. Maintains per-session conversation
context (without PII — already tokenised by middleware).
"""

import json
import logging
import time

from backend.agents.base_agent import BaseAgent, AgentResponse
from backend.data.schemas import UserState
from backend.llm.provider import LLMProvider

logger = logging.getLogger(__name__)

# Intent categories the classifier outputs
VALID_INTENTS = frozenset({
    "credit_inquiry",
    "financial_advice",
    "bank_faq",
    "onboarding",
    "greeting",
})

# Short, fast classification prompt — returns JSON only
_CLASSIFY_PROMPT = """\
Eres un clasificador de intenciones para un asistente bancario colombiano.
Dada la frase del usuario, responde SOLO con un JSON:
{"intent": "<categoría>"}

Categorías:
- credit_inquiry: preguntas sobre crédito, préstamo, microcrédito, si califico, cuánto me prestan
- financial_advice: mejorar puntaje, tips financieros, plan de ahorro, misiones, cómo mejorar
- bank_faq: horarios, sucursales, productos, transferencias, cuentas, CDT, tarifas, operaciones
- onboarding: abrir cuenta, no soy cliente, quiero registrarme, bancarizarme
- greeting: saludo, hola, buenas, cómo estás

Responde ÚNICAMENTE el JSON, sin texto adicional."""


# -----------------------------------------------------------------------
# Intent cache — avoids repeated LLM calls for similar messages
# -----------------------------------------------------------------------

class _IntentCache:
    """Simple TTL cache mapping normalised message text → (intent, timestamp)."""

    def __init__(self, max_size: int = 200, ttl_seconds: float = 300):
        self._store: dict[str, tuple[str, float]] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds

    def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        intent, ts = entry
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return None
        return intent

    def put(self, key: str, intent: str) -> None:
        if len(self._store) >= self._max_size:
            # Evict oldest
            oldest_key = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest_key]
        self._store[key] = (intent, time.monotonic())

    @staticmethod
    def normalise(text: str) -> str:
        return " ".join(text.lower().strip().split())


# -----------------------------------------------------------------------
# Session context store
# -----------------------------------------------------------------------

class _SessionStore:
    """In-memory per-session conversation context.

    Stores the last N messages and agent state per session_id.
    In production this would be backed by DynamoDB.
    """

    def __init__(self, max_history: int = 20):
        self._sessions: dict[str, dict] = {}
        self._max_history = max_history

    def get(self, session_id: str) -> dict:
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "history": [],
                "current_agent": None,
                "handoff_count": 0,
            }
        return self._sessions[session_id]

    def append_turn(self, session_id: str, role: str, content: str, agent_name: str | None = None) -> None:
        ctx = self.get(session_id)
        ctx["history"].append({
            "role": role,
            "content": content,
            "agent": agent_name,
        })
        # Trim to max
        if len(ctx["history"]) > self._max_history:
            ctx["history"] = ctx["history"][-self._max_history:]

    def set_agent(self, session_id: str, agent_name: str) -> None:
        ctx = self.get(session_id)
        ctx["current_agent"] = agent_name

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


# -----------------------------------------------------------------------
# Orchestrator
# -----------------------------------------------------------------------

# Intent → agent name mapping
_INTENT_TO_AGENT = {
    "credit_inquiry": "credit_evaluator",
    "financial_advice": "financial_advisor",
    "bank_faq": "helpyy_general",
    "onboarding": "onboarding",
    "greeting": "helpyy_general",
}


class Orchestrator:
    """Router principal: classifies user intent and dispatches to the right agent.

    Routing priority:
        1. Not banked → always OnboardingAgent (regardless of intent)
        2. Classify intent with LLM
        3. Dispatch to matching agent
        4. Fallback to HelpyyGeneralAgent
    """

    def __init__(self, llm: LLMProvider, agents: dict[str, BaseAgent]):
        self.llm = llm
        self.agents = agents
        self._cache = _IntentCache()
        self._sessions = _SessionStore()

    async def handle_message(
        self, message: str, session_id: str, user_state: UserState,
        *, original_message: str | None = None,
    ) -> AgentResponse:
        """Full flow: classify → route → process → store context → return."""
        # Store user message in session
        self._sessions.append_turn(session_id, "user", message)
        context = self._sessions.get(session_id)

        # Route to the right agent
        agent = await self.route(message, user_state)
        self._sessions.set_agent(session_id, agent.name)
        logger.info(
            "[ORCHESTRATOR] session=%s | is_banked=%s | routed_to=%s | msg=%.50s",
            session_id, user_state.is_banked, agent.name, message[:50],
        )

        # Process — pass original (untokenized) message for data extraction
        response = await agent.process(message, context, original_message=original_message)
        logger.info(
            "[ORCHESTRATOR] agent=%s | response_len=%d | handoff=%s | metadata_keys=%s",
            agent.name, len(response.content), response.handoff_to, list(response.metadata.keys()),
        )

        # Store assistant response
        self._sessions.append_turn(
            session_id, "assistant", response.content, agent_name=agent.name,
        )

        # Handle handoff if the agent requested one
        if response.handoff_to and response.handoff_to in self.agents:
            response = await self.handle_handoff(
                from_agent=agent.name,
                to_agent=response.handoff_to,
                context=context,
                session_id=session_id,
                original_message=original_message or message,
            )

        return response

    async def route(self, message: str, user_state: UserState) -> BaseAgent:
        """Determine which agent should handle this message."""
        # Rule 1: unbanked users always go to onboarding
        if not user_state.is_banked and "onboarding" in self.agents:
            return self.agents["onboarding"]

        # Rule 2: classify intent
        intent = await self.classify_intent(message)
        agent_name = _INTENT_TO_AGENT.get(intent, "helpyy_general")

        # Rule 3: fallback if agent not registered
        if agent_name not in self.agents:
            agent_name = "helpyy_general"

        return self.agents[agent_name]

    async def classify_intent(self, message: str) -> str:
        """Use LLM with a lightweight prompt. Returns one of VALID_INTENTS.

        Results are cached by normalised message text to avoid redundant calls.
        """
        key = _IntentCache.normalise(message)

        # Check cache first
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        # Call LLM
        messages = [
            {"role": "system", "content": _CLASSIFY_PROMPT},
            {"role": "user", "content": message},
        ]
        raw = await self.llm.generate(messages, temperature=0.0)

        # Parse JSON response
        intent = self._parse_intent(raw)
        self._cache.put(key, intent)
        return intent

    async def handle_handoff(
        self,
        from_agent: str,
        to_agent: str,
        context: dict,
        session_id: str,
        original_message: str = "",
    ) -> AgentResponse:
        """Manage smooth transitions between agents, preserving context."""
        target = self.agents.get(to_agent)
        if target is None:
            logger.warning("Handoff target %r not found, staying with %r", to_agent, from_agent)
            return AgentResponse(
                content="Lo siento, hubo un problema al transferirte. ¿En qué más puedo ayudarte?",
                agent_name=from_agent,
            )

        # Update session
        context["handoff_count"] = context.get("handoff_count", 0) + 1
        context["previous_agent"] = from_agent
        self._sessions.set_agent(session_id, to_agent)

        # Build a transition context — tell the new agent what happened
        transition_msg = (
            f"[El usuario fue transferido desde el agente {from_agent}. "
            f"Continúa la conversación de forma natural. "
            f"El último mensaje del usuario fue: \"{original_message}\"]"
        )
        context_with_transition = dict(context)
        history = list(context.get("history", []))
        history.append({"role": "system", "content": transition_msg})
        context_with_transition["history"] = history

        # Process with the new agent
        response = await target.process(
            original_message, context_with_transition,
            original_message=original_message,
        )
        response.metadata["handoff_from"] = from_agent

        # Store the response
        self._sessions.append_turn(
            session_id, "assistant", response.content, agent_name=to_agent,
        )

        return response

    async def handle_message_stream(
        self, message: str, session_id: str, user_state: UserState,
        *, original_message: str | None = None,
    ):
        """Streaming variant of handle_message — yields dicts for WebSocket.

        Yields events in order:
            {"type": "token", "content": "word", "agent": "agent_name"}
            ...
            {"type": "done", "agent": "name", "suggested_actions": [...], "handoff_to": ...}
            {"type": "agent_change", "from": "old", "to": "new"}  (if handoff)
            # If handoff, streams the new agent's response too:
            {"type": "token", "content": "word", "agent": "new_agent"}
            {"type": "done", "agent": "new_agent", ...}

        PII safety: the caller must tokenize the inbound message and
        detokenize each yielded content string.  We operate on
        already-tokenized text here and return tokenized text — the
        chat router handles the PII boundary.
        """
        # Store user message
        self._sessions.append_turn(session_id, "user", message)
        context = self._sessions.get(session_id)

        # Route
        agent = await self.route(message, user_state)
        self._sessions.set_agent(session_id, agent.name)

        # Get full response (needed for metadata + handoff detection)
        response = await agent.process(message, context, original_message=original_message)

        # Store assistant turn
        self._sessions.append_turn(
            session_id, "assistant", response.content, agent_name=agent.name,
        )

        # Stream content word-by-word
        words = response.content.split(" ")
        for i, word in enumerate(words):
            token = word if i == 0 else " " + word
            yield {"type": "token", "content": token, "agent": response.agent_name}

        # Done event with metadata
        yield {
            "type": "done",
            "agent": response.agent_name,
            "suggested_actions": response.suggested_actions,
            "handoff_to": response.handoff_to,
            "metadata": response.metadata,
        }

        # Handle handoff
        if response.handoff_to and response.handoff_to in self.agents:
            from_agent = agent.name
            to_agent = response.handoff_to

            yield {"type": "agent_change", "from": from_agent, "to": to_agent}

            handoff_response = await self.handle_handoff(
                from_agent=from_agent,
                to_agent=to_agent,
                context=context,
                session_id=session_id,
                original_message=original_message or message,
            )

            # Stream the handoff agent's response
            words = handoff_response.content.split(" ")
            for i, word in enumerate(words):
                token = word if i == 0 else " " + word
                yield {"type": "token", "content": token, "agent": handoff_response.agent_name}

            yield {
                "type": "done",
                "agent": handoff_response.agent_name,
                "suggested_actions": handoff_response.suggested_actions,
                "handoff_to": handoff_response.handoff_to,
                "metadata": handoff_response.metadata,
            }

    def get_session_context(self, session_id: str) -> dict:
        """Get the current session context (for testing/debugging)."""
        return self._sessions.get(session_id)

    def clear_session(self, session_id: str) -> None:
        """Clear a session's context."""
        self._sessions.delete(session_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_intent(raw: str) -> str:
        """Extract intent from LLM response. Tolerates messy output."""
        text = raw.strip()

        # Try JSON parse first
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                obj = json.loads(text[start : end + 1])
                intent = obj.get("intent", "").strip().lower()
                if intent in VALID_INTENTS:
                    return intent
            except (json.JSONDecodeError, AttributeError):
                pass

        # Fallback: look for any known intent keyword in the text
        text_lower = text.lower()
        for intent in VALID_INTENTS:
            if intent in text_lower:
                return intent

        # Ultimate fallback
        return "bank_faq"
