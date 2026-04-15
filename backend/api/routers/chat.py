"""Chat router — POST /chat with streaming + WebSocket /ws/chat.

Handles PII tokenization/detokenization for both HTTP and WebSocket paths.
The HTTP PII middleware covers POST /chat, but WebSocket bypasses middleware,
so this module applies PII processing directly in the WS handler.
"""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from backend.api.middleware.rate_limiter import limiter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.agents.orchestrator import Orchestrator
from backend.api.activation_codes import get_activation_store
from backend.data.schemas import UserState
from backend.security.pii_tokenizer import tokenize_pii
from backend.security.pii_detokenizer import detokenize_response, get_vault
from backend.security.audit_logger import log_pii_access

router = APIRouter()
logger = logging.getLogger(__name__)

# Module-level orchestrator — lazily initialised
_orchestrator: Orchestrator | None = None


def _get_orchestrator() -> Orchestrator:
    """Create orchestrator with all registered agents."""
    global _orchestrator
    if _orchestrator is None:
        from backend.llm.config import get_llm_provider

        llm = get_llm_provider()

        # Import and instantiate all agents
        from backend.agents.helpyy_general_agent import HelpyyGeneralAgent
        from backend.agents.credit_evaluator_agent import CreditEvaluatorAgent
        from backend.agents.financial_advisor_agent import FinancialAdvisorAgent
        from backend.agents.onboarding_agent import OnboardingAgent

        agents = {
            "helpyy_general": HelpyyGeneralAgent(llm),
            "credit_evaluator": CreditEvaluatorAgent(llm),
            "financial_advisor": FinancialAdvisorAgent(llm),
            "onboarding": OnboardingAgent(llm),
        }
        _orchestrator = Orchestrator(llm, agents)
    return _orchestrator


def set_orchestrator(orch: Orchestrator) -> None:
    """Dependency injection for testing."""
    global _orchestrator
    _orchestrator = orch


# ───────── PII helpers for WebSocket ─────────


def _tokenize_text(text: str, session_id: str) -> str:
    """Tokenize PII in user message and store mapping in vault."""
    tokenized, mapping = tokenize_pii(text)
    if len(mapping) > 1:  # more than just _types
        vault = get_vault()
        vault.store(session_id, mapping)
        for token in mapping:
            if token != "_types":
                log_pii_access(session_id, "tokenize", token, "websocket_inbound")
    return tokenized


def _detokenize_text(text: str, session_id: str) -> str:
    """Detokenize PII tokens in agent response."""
    return detokenize_response(text, session_id)


def _maybe_generate_activation_code(safe_meta: dict, session_id: str) -> dict:
    """If metadata signals onboarding completion, generate an activation code."""
    if safe_meta.get("helpyy_enabled") and safe_meta.get("account_id"):
        store = get_activation_store()
        code = store.generate(
            session_id=session_id,
            account_id=safe_meta["account_id"],
            display_name=safe_meta.get("display_name", ""),
        )
        safe_meta["activation_code"] = code
    return safe_meta


# ───────── Request / Response models ─────────


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    stream: bool = False
    user_id: str | None = None
    is_banked: bool = True


class ChatResponse(BaseModel):
    content: str
    agent_name: str
    agent_type: str
    suggested_actions: list[str] = []
    handoff_to: str | None = None
    metadata: dict = {}


# ───────── HTTP Endpoints ─────────


@router.post("/chat")
@limiter.limit("30/minute")
async def chat(request: Request, body: ChatRequest):
    """Process a chat message through the orchestrator.

    If stream=true, returns SSE text/event-stream.
    Otherwise returns JSON ChatResponse.

    PII: tokenization is handled here (not in middleware) so the original
    message is available for data extraction by agents like OnboardingAgent.
    """
    orchestrator = _get_orchestrator()

    user = UserState(
        user_id=body.user_id or body.session_id,
        is_banked=body.is_banked,
    )

    # Tokenize here (not in middleware) so we keep access to the original
    raw_message = body.message
    tokenized_message = _tokenize_text(raw_message, body.session_id)
    logger.info("[HTTP] POST /chat: session=%s | is_banked=%s | stream=%s | msg=%.50s",
                body.session_id, body.is_banked, body.stream, raw_message[:50])

    if body.stream:
        return StreamingResponse(
            _stream_response(orchestrator, body, user, tokenized_message, raw_message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming: full response
    response = await orchestrator.handle_message(
        tokenized_message, body.session_id, user,
        original_message=raw_message,
    )

    # Detokenize response content and metadata (middleware is skipped for /chat)
    safe_content = _detokenize_text(response.content, body.session_id)
    raw_meta = response.metadata or {}
    safe_meta = {
        k: _detokenize_text(str(v), body.session_id) if isinstance(v, str) else v
        for k, v in raw_meta.items()
    }
    safe_meta = _maybe_generate_activation_code(safe_meta, body.session_id)

    return ChatResponse(
        content=safe_content,
        agent_name=response.agent_name,
        agent_type=response.agent_type,
        suggested_actions=response.suggested_actions,
        handoff_to=response.handoff_to,
        metadata=safe_meta,
    )


async def _stream_response(orchestrator, body, user, tokenized_message, raw_message):
    """SSE generator using orchestrator streaming with PII detokenization."""
    try:
        async for event in orchestrator.handle_message_stream(
            tokenized_message, body.session_id, user,
            original_message=raw_message,
        ):
            if event["type"] == "token":
                # Detokenize each token chunk
                content = _detokenize_text(event["content"], body.session_id)
                data = json.dumps({"token": content, "agent": event.get("agent")})
                yield f"data: {data}\n\n"

            elif event["type"] == "done":
                raw_meta = event.get("metadata", {})
                safe_meta = {
                    k: _detokenize_text(str(v), body.session_id) if isinstance(v, str) else v
                    for k, v in raw_meta.items()
                }
                safe_meta = _maybe_generate_activation_code(safe_meta, body.session_id)
                final = json.dumps({
                    "token": "",
                    "done": True,
                    "agent_name": event["agent"],
                    "suggested_actions": event.get("suggested_actions", []),
                    "handoff_to": event.get("handoff_to"),
                    "metadata": safe_meta,
                })
                yield f"data: {final}\n\n"

            elif event["type"] == "agent_change":
                change = json.dumps({
                    "agent_change": True,
                    "from": event["from"],
                    "to": event["to"],
                })
                yield f"data: {change}\n\n"

        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.exception("SSE stream error")
        error = json.dumps({"error": str(e)})
        yield f"data: {error}\n\n"


# ───────── WebSocket Endpoint ─────────


@router.websocket("/ws/chat/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time streaming chat.

    PII is handled directly here (middleware doesn't cover WebSocket).

    Inbound protocol:
        {"type": "message", "content": "user text", "is_banked": true}

    Outbound protocol:
        {"type": "token",        "content": "word", "agent": "agent_name"}
        {"type": "done",         "agent": "name", "suggested_actions": [...]}
        {"type": "agent_change", "from": "old", "to": "new"}
        {"type": "error",        "content": "description"}
        {"type": "connected",    "session_id": "..."}
    """
    await websocket.accept()
    orchestrator = _get_orchestrator()
    logger.info("[WS] Connected: session=%s", session_id)

    # Send connection confirmation
    await websocket.send_json({
        "type": "connected",
        "session_id": session_id,
    })

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") != "message":
                continue

            content = data.get("content", "").strip()
            if not content:
                continue

            is_banked = data.get("is_banked", True)
            user = UserState(user_id=session_id, is_banked=is_banked)
            logger.info("[WS] Message: session=%s | is_banked=%s | msg=%.50s", session_id, is_banked, content[:50])

            # ── PII: tokenize inbound message ──
            tokenized_content = _tokenize_text(content, session_id)

            try:
                # Stream response events — pass original for data extraction
                async for event in orchestrator.handle_message_stream(
                    tokenized_content, session_id, user,
                    original_message=content,
                ):
                    if event["type"] == "token":
                        # PII: detokenize outbound content
                        safe_content = _detokenize_text(
                            event["content"], session_id,
                        )
                        await websocket.send_json({
                            "type": "token",
                            "content": safe_content,
                            "agent": event.get("agent"),
                        })

                    elif event["type"] == "done":
                        raw_meta = event.get("metadata", {})
                        safe_meta = {
                            k: _detokenize_text(str(v), session_id) if isinstance(v, str) else v
                            for k, v in raw_meta.items()
                        }
                        safe_meta = _maybe_generate_activation_code(safe_meta, session_id)
                        await websocket.send_json({
                            "type": "done",
                            "agent": event["agent"],
                            "suggested_actions": event.get("suggested_actions", []),
                            "handoff_to": event.get("handoff_to"),
                            "metadata": safe_meta,
                        })

                    elif event["type"] == "agent_change":
                        await websocket.send_json({
                            "type": "agent_change",
                            "from": event["from"],
                            "to": event["to"],
                        })

            except Exception as e:
                logger.exception("Error processing WS message")
                await websocket.send_json({
                    "type": "error",
                    "content": f"Error procesando tu mensaje: {e}",
                })

    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected: session=%s", session_id)
    except Exception as e:
        logger.exception("WebSocket unexpected error: session=%s", session_id)
        try:
            await websocket.send_json({"type": "error", "content": str(e)})
            await websocket.close()
        except Exception:
            pass
