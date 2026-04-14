"""Integration tests — WebSocket + HTTP chat communication.

Tests the full path: frontend message → router → PII tokenize →
orchestrator → agent → PII detokenize → response to frontend.

Uses Starlette TestClient (sync WebSocket) + httpx for HTTP SSE.
"""

import json

import pytest
from starlette.testclient import TestClient

from backend.agents.base_agent import AgentResponse
from backend.agents.orchestrator import Orchestrator
from backend.api.main import app
from backend.api.routers.chat import set_orchestrator
from backend.data.schemas import UserState
from backend.llm.provider import LLMProvider
from backend.security.pii_tokenizer import tokenize_pii
from backend.security.pii_vault import PIIVault
from backend.security.pii_detokenizer import set_vault as set_detok_vault


# ───────── Fake LLM that returns predictable output ─────────


class _FakeLLM(LLMProvider):
    """Deterministic LLM for integration tests."""

    def __init__(self, response: str = "Hola, te puedo ayudar."):
        self._response = response

    async def generate(self, messages, **kwargs):
        return self._response

    async def generate_stream(self, messages, **kwargs):
        for word in self._response.split():
            yield word + " "

    async def generate_with_tools(self, messages, tools, **kwargs):
        return self._response


# ───────── Fake agent that records what it receives ─────────


class _SpyAgent:
    """Agent that records inbound messages and returns canned responses."""

    name = "helpyy_general"
    system_prompt = ""
    tools = []
    _tool_handlers = {}

    def __init__(self, response_content="Respuesta del agente.",
                 handoff_to=None, suggested_actions=None):
        self._response_content = response_content
        self._handoff_to = handoff_to
        self._suggested_actions = suggested_actions or []
        self.received_messages = []

    async def process(self, message, context):
        self.received_messages.append(message)
        return AgentResponse(
            content=self._response_content,
            agent_name=self.name,
            agent_type="general",
            handoff_to=self._handoff_to,
            suggested_actions=self._suggested_actions,
        )

    async def process_stream(self, message, context):
        for word in self._response_content.split():
            yield word + " "


class _HandoffTargetAgent(_SpyAgent):
    """Agent that serves as a handoff target."""

    name = "credit_evaluator"

    def __init__(self):
        super().__init__(
            response_content="Voy a revisar tu perfil crediticio.",
            suggested_actions=["Ver opciones de credito"],
        )


# ───────── Fixtures ─────────


@pytest.fixture()
def spy_agent():
    return _SpyAgent(
        response_content="Hola Carlos, te puedo ayudar con eso.",
        suggested_actions=["Ver productos", "Consultar saldo"],
    )


@pytest.fixture()
def handoff_agent():
    """General agent that triggers handoff to credit_evaluator."""
    return _SpyAgent(
        response_content="Te conecto con el evaluador de credito.",
        handoff_to="credit_evaluator",
    )


@pytest.fixture()
def target_agent():
    return _HandoffTargetAgent()


@pytest.fixture()
def orchestrator_simple(spy_agent):
    """Orchestrator with a single general agent (no LLM classification needed)."""
    llm = _FakeLLM()
    return Orchestrator(llm, {"helpyy_general": spy_agent})


@pytest.fixture()
def orchestrator_with_handoff(handoff_agent, target_agent):
    """Orchestrator that will trigger a handoff."""
    llm = _FakeLLM()
    return Orchestrator(llm, {
        "helpyy_general": handoff_agent,
        "credit_evaluator": target_agent,
    })


@pytest.fixture()
def pii_vault(tmp_path):
    """Fresh PII vault backed by a temp SQLite DB."""
    vault = PIIVault(db_path=str(tmp_path / "test_pii.db"), ttl_hours=1)
    set_detok_vault(vault)
    yield vault
    set_detok_vault(None)


@pytest.fixture()
def client(orchestrator_simple):
    """Starlette TestClient with injected orchestrator."""
    set_orchestrator(orchestrator_simple)
    yield TestClient(app)
    set_orchestrator(None)


@pytest.fixture()
def client_handoff(orchestrator_with_handoff):
    """TestClient with handoff-capable orchestrator."""
    set_orchestrator(orchestrator_with_handoff)
    yield TestClient(app)
    set_orchestrator(None)


# ═══════════════════════════════════════════════════════════════
# Test: WebSocket connects and receives confirmation
# ═══════════════════════════════════════════════════════════════


class TestWebSocketConnects:

    def test_ws_connect_receives_connected_event(self, client):
        with client.websocket_connect("/api/v1/ws/chat/test-session") as ws:
            data = ws.receive_json()
            assert data["type"] == "connected"
            assert data["session_id"] == "test-session"

    def test_ws_connect_different_sessions(self, client):
        with client.websocket_connect("/api/v1/ws/chat/session-a") as ws:
            data = ws.receive_json()
            assert data["session_id"] == "session-a"

        with client.websocket_connect("/api/v1/ws/chat/session-b") as ws:
            data = ws.receive_json()
            assert data["session_id"] == "session-b"

    def test_ws_ignores_non_message_types(self, client):
        """Sending a non-'message' type should not trigger a response."""
        with client.websocket_connect("/api/v1/ws/chat/test-session") as ws:
            ws.receive_json()  # connected
            ws.send_json({"type": "ping"})
            # Send a real message to prove the connection is still alive
            ws.send_json({"type": "message", "content": "hola"})
            events = _collect_until_done(ws)
            assert any(e["type"] == "token" for e in events)


# ═══════════════════════════════════════════════════════════════
# Test: Message streams correctly
# ═══════════════════════════════════════════════════════════════


class TestMessageStreams:

    def test_tokens_arrive_in_order(self, client, spy_agent):
        with client.websocket_connect("/api/v1/ws/chat/stream-test") as ws:
            ws.receive_json()  # connected
            ws.send_json({"type": "message", "content": "hola"})

            events = _collect_until_done(ws)
            tokens = [e["content"] for e in events if e["type"] == "token"]

            # Reconstruct full text from tokens
            full = "".join(tokens)
            assert full == spy_agent._response_content

    def test_done_event_contains_metadata(self, client, spy_agent):
        with client.websocket_connect("/api/v1/ws/chat/meta-test") as ws:
            ws.receive_json()  # connected
            ws.send_json({"type": "message", "content": "ver productos"})

            events = _collect_until_done(ws)
            done = [e for e in events if e["type"] == "done"]

            assert len(done) == 1
            assert done[0]["agent"] == "helpyy_general"
            assert done[0]["suggested_actions"] == ["Ver productos", "Consultar saldo"]

    def test_token_events_include_agent_name(self, client):
        with client.websocket_connect("/api/v1/ws/chat/agent-test") as ws:
            ws.receive_json()  # connected
            ws.send_json({"type": "message", "content": "hola"})

            events = _collect_until_done(ws)
            token_events = [e for e in events if e["type"] == "token"]

            assert all(e["agent"] == "helpyy_general" for e in token_events)

    def test_empty_message_is_ignored(self, client, spy_agent):
        with client.websocket_connect("/api/v1/ws/chat/empty-test") as ws:
            ws.receive_json()  # connected
            ws.send_json({"type": "message", "content": ""})
            ws.send_json({"type": "message", "content": "   "})
            # Now send a real message
            ws.send_json({"type": "message", "content": "real"})
            events = _collect_until_done(ws)
            assert any(e["type"] == "token" for e in events)
            # Agent should only have received the real message
            assert len(spy_agent.received_messages) == 1

    def test_http_sse_fallback_streams(self, client, spy_agent):
        """POST /chat with stream=true should return SSE text/event-stream."""
        resp = client.post(
            "/api/v1/chat",
            json={"message": "hola", "session_id": "sse-test", "stream": True},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        # Parse SSE events
        lines = resp.text.strip().split("\n")
        data_lines = [l for l in lines if l.startswith("data: ")]
        assert len(data_lines) >= 2  # at least one token + [DONE]

        # Last data line should be [DONE]
        assert data_lines[-1] == "data: [DONE]"

        # Find the done event
        for dl in data_lines:
            payload = dl[6:]
            if payload == "[DONE]":
                continue
            parsed = json.loads(payload)
            if parsed.get("done"):
                assert parsed["agent_name"] == "helpyy_general"
                break

    def test_http_json_response(self, client, spy_agent):
        """POST /chat without stream should return JSON."""
        resp = client.post(
            "/api/v1/chat",
            json={"message": "hola", "session_id": "json-test", "stream": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == "helpyy_general"
        assert data["content"] == spy_agent._response_content


# ═══════════════════════════════════════════════════════════════
# Test: Agent handoff notifies frontend
# ═══════════════════════════════════════════════════════════════


class TestAgentHandoff:

    def test_handoff_sends_agent_change_event(self, client_handoff):
        with client_handoff.websocket_connect("/api/v1/ws/chat/handoff-test") as ws:
            ws.receive_json()  # connected
            ws.send_json({"type": "message", "content": "quiero un credito"})

            events = _collect_all_events(ws)

            # Should have: tokens from general, done, agent_change, tokens from evaluator, done
            agent_changes = [e for e in events if e["type"] == "agent_change"]
            assert len(agent_changes) == 1
            assert agent_changes[0]["from"] == "helpyy_general"
            assert agent_changes[0]["to"] == "credit_evaluator"

    def test_handoff_streams_new_agent_response(self, client_handoff, target_agent):
        with client_handoff.websocket_connect("/api/v1/ws/chat/handoff-stream") as ws:
            ws.receive_json()  # connected
            ws.send_json({"type": "message", "content": "quiero un credito"})

            events = _collect_all_events(ws)

            # Find done events — should be 2 (one per agent)
            done_events = [e for e in events if e["type"] == "done"]
            assert len(done_events) == 2
            assert done_events[0]["agent"] == "helpyy_general"
            assert done_events[1]["agent"] == "credit_evaluator"

    def test_handoff_second_agent_tokens_arrive(self, client_handoff, target_agent):
        with client_handoff.websocket_connect("/api/v1/ws/chat/handoff-tokens") as ws:
            ws.receive_json()  # connected
            ws.send_json({"type": "message", "content": "prestamo"})

            events = _collect_all_events(ws)

            # Tokens after agent_change should be from credit_evaluator
            saw_change = False
            post_change_tokens = []
            for e in events:
                if e["type"] == "agent_change":
                    saw_change = True
                elif saw_change and e["type"] == "token":
                    post_change_tokens.append(e)

            assert len(post_change_tokens) > 0
            assert all(t["agent"] == "credit_evaluator" for t in post_change_tokens)
            full = "".join(t["content"] for t in post_change_tokens)
            assert full == target_agent._response_content


# ═══════════════════════════════════════════════════════════════
# Test: PII is not exposed in WebSocket messages
# ═══════════════════════════════════════════════════════════════


class TestPIINotInWebSocket:

    def test_cedula_tokenized_before_agent(self, pii_vault):
        """A cedula in the user message must be tokenized before the agent sees it."""
        spy = _SpyAgent(response_content="Revisando tu perfil.")
        llm = _FakeLLM()
        orch = Orchestrator(llm, {"helpyy_general": spy})
        set_orchestrator(orch)

        try:
            with TestClient(app) as tc:
                with tc.websocket_connect("/api/v1/ws/chat/pii-test") as ws:
                    ws.receive_json()  # connected
                    ws.send_json({
                        "type": "message",
                        "content": "Mi cedula es 1234567890",
                    })
                    _collect_until_done(ws)

            # The agent should have received a tokenized version
            assert len(spy.received_messages) == 1
            msg = spy.received_messages[0]
            assert "1234567890" not in msg
            assert "[TOK_CC_" in msg
        finally:
            set_orchestrator(None)

    def test_name_tokenized_before_agent(self, pii_vault):
        """A name with 'me llamo' pattern must be tokenized."""
        spy = _SpyAgent(response_content="Hola, bienvenido.")
        llm = _FakeLLM()
        orch = Orchestrator(llm, {"helpyy_general": spy})
        set_orchestrator(orch)

        try:
            with TestClient(app) as tc:
                with tc.websocket_connect("/api/v1/ws/chat/pii-name") as ws:
                    ws.receive_json()  # connected
                    ws.send_json({
                        "type": "message",
                        "content": "Me llamo Juan Perez",
                    })
                    _collect_until_done(ws)

            msg = spy.received_messages[0]
            assert "Juan Perez" not in msg
            assert "[TOK_NAME_" in msg
        finally:
            set_orchestrator(None)

    def test_pii_token_detokenized_in_response(self, pii_vault):
        """If the agent response contains a PII token, it should be detokenized
        to a safe partial value before reaching the frontend."""
        # First, tokenize to get a real token
        tokenized, mapping = tokenize_pii("Mi cedula es 1234567890")
        session_id = "pii-detok-test"
        pii_vault.store(session_id, mapping)

        # Find the token
        cc_token = [t for t in mapping if t.startswith("[TOK_CC_")][0]

        # Agent responds WITH the token (as it would after processing tokenized input)
        spy = _SpyAgent(response_content=f"Tu cedula {cc_token} esta registrada.")
        llm = _FakeLLM()
        orch = Orchestrator(llm, {"helpyy_general": spy})
        set_orchestrator(orch)

        try:
            with TestClient(app) as tc:
                with tc.websocket_connect(f"/api/v1/ws/chat/{session_id}") as ws:
                    ws.receive_json()  # connected
                    ws.send_json({"type": "message", "content": "hola"})
                    events = _collect_until_done(ws)

            tokens = [e["content"] for e in events if e["type"] == "token"]
            full = "".join(tokens)

            # Should NOT contain the raw token
            assert cc_token not in full
            # Should contain the masked version
            assert "****7890" in full
        finally:
            set_orchestrator(None)

    def test_raw_cedula_never_in_outbound_tokens(self, pii_vault):
        """No outbound WebSocket message should contain the raw cedula."""
        spy = _SpyAgent(response_content="Datos recibidos correctamente.")
        llm = _FakeLLM()
        orch = Orchestrator(llm, {"helpyy_general": spy})
        set_orchestrator(orch)

        try:
            with TestClient(app) as tc:
                with tc.websocket_connect("/api/v1/ws/chat/pii-outbound") as ws:
                    ws.receive_json()  # connected
                    ws.send_json({
                        "type": "message",
                        "content": "Mi cedula es 9876543210 y me llamo Maria Lopez",
                    })
                    events = _collect_until_done(ws)

            # Check ALL events for raw PII leaks
            for event in events:
                event_str = json.dumps(event)
                assert "9876543210" not in event_str
                assert "Maria Lopez" not in event_str
        finally:
            set_orchestrator(None)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


def _collect_until_done(ws, timeout_events=50):
    """Collect WebSocket events until a 'done' event or max events reached."""
    events = []
    for _ in range(timeout_events):
        data = ws.receive_json()
        events.append(data)
        if data.get("type") == "done":
            break
    return events


def _collect_all_events(ws, timeout_events=100):
    """Collect all events including handoff (may have 2 done events).

    A handoff sequence is: tokens → done(handoff_to=X) → agent_change → tokens → done.
    We keep collecting after the first done if it has a handoff_to field.
    """
    events = []
    done_count = 0
    expect_more = False
    for _ in range(timeout_events):
        data = ws.receive_json()
        events.append(data)
        if data.get("type") == "done":
            done_count += 1
            if data.get("handoff_to"):
                # More events coming (agent_change + second agent stream)
                expect_more = True
            elif expect_more and done_count >= 2:
                break
            else:
                break
    return events
