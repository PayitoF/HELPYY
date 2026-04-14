"""Base agent — abstract class all agents inherit from.

Provides the LLM integration layer: message building, tool execution loop,
streaming, and structured responses. Concrete agents only need to define
their name, system_prompt, tools, and optionally override _build_messages.
"""

from abc import ABC
import time
from typing import Any, AsyncIterator, Callable, Coroutine

from pydantic import BaseModel

from backend.llm.provider import LLMProvider, ToolCallResult, ToolDefinition
from backend.observability.llm_logger import log_llm_call


# -----------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------

class Tool(BaseModel):
    """Definition of a tool an agent can use.

    The handler is NOT part of the schema — it is registered separately
    via the agent's _tool_handlers dict so the JSON schema stays clean.
    """

    name: str
    description: str
    parameters: dict  # JSON Schema


class AgentResponse(BaseModel):
    """Structured response from an agent."""

    content: str
    agent_name: str
    agent_type: str = "general"
    suggested_actions: list[str] = []
    metadata: dict = {}
    handoff_to: str | None = None


# Type alias for async tool handler functions
ToolHandler = Callable[..., Coroutine[Any, Any, str]]


# -----------------------------------------------------------------------
# BaseAgent
# -----------------------------------------------------------------------

class BaseAgent(ABC):
    """Abstract base for all Helpyy Hand agents.

    Subclasses must set:
        - name: str
        - system_prompt: str
        - tools: list[Tool]

    And may override:
        - _build_messages(message, context) to customise prompt construction
        - _tool_handlers: dict mapping tool name → async handler function
    """

    name: str = "base"
    system_prompt: str = ""
    tools: list[Tool] = []

    # Subclasses populate this: {"tool_name": async_handler_fn}
    _tool_handlers: dict[str, ToolHandler] = {}

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def process(self, message: str, context: dict, *, original_message: str | None = None) -> AgentResponse:
        """Process a user message and return a structured response.

        Args:
            message: The (tokenized) user message for LLM consumption.
            context: Session context dict.
            original_message: The raw untokenized message — used by agents
                that need to extract structured data (e.g. OnboardingAgent).
                Never passed to the LLM.

        If the agent has tools, enters a tool-use loop (max 5 iterations)
        where the LLM can call tools and the results are appended as
        messages until the LLM produces a final text response.
        """
        messages = self._build_messages(message, context)

        t0 = time.perf_counter()
        err = None
        try:
            if self.tools and self._tool_handlers:
                content = await self._run_with_tools(messages, context)
            else:
                content = await self.llm.generate(messages, temperature=0.7)
        except Exception as e:
            err = str(e)
            raise
        finally:
            latency = (time.perf_counter() - t0) * 1000
            sid = context.get("history", [{}])[0].get("agent", "") if context.get("history") else ""
            log_llm_call(
                session_id=sid,
                agent=self.name,
                latency_ms=latency,
                tokens_in=sum(len(m.get("content", "")) // 4 for m in messages),
                tokens_out=len(content) // 4 if not err else 0,
                error=err,
            )

        return self._make_response(content, context)

    async def process_stream(
        self, message: str, context: dict,
        *, original_message: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream response tokens. Does NOT support tool calling mid-stream."""
        messages = self._build_messages(message, context)
        async for token in self.llm.generate_stream(messages, temperature=0.7):
            yield token

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_messages(self, message: str, context: dict) -> list[dict]:
        """Build the message list for the LLM.

        Default: system prompt + conversation history (user/assistant only).
        The orchestrator appends the current user turn to history before calling
        process(), so it is always the last item — we do NOT add it again.
        Only user/assistant roles are included; mid-history system messages
        confuse smaller models and produce empty output.
        """
        messages: list[dict] = []

        # System prompt (first position — models expect it here)
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # Conversation history (last N turns, no PII — already tokenised)
        history = context.get("history", [])
        for turn in history[-10:]:  # keep last 10 turns for context window
            if turn["role"] in ("user", "assistant"):
                messages.append({"role": turn["role"], "content": turn["content"]})

        return messages

    # ------------------------------------------------------------------
    # Tool execution loop
    # ------------------------------------------------------------------

    async def _run_with_tools(self, messages: list[dict], context: dict) -> str:
        """LLM ↔ tool loop. Max 5 iterations to prevent runaway."""
        tool_defs = [
            ToolDefinition(name=t.name, description=t.description, parameters=t.parameters)
            for t in self.tools
        ]

        working_messages = list(messages)

        for _ in range(5):
            result = await self.llm.generate_with_tools(
                working_messages, tool_defs, temperature=0.7,
            )

            # If LLM returned text (no tool call), we're done
            if isinstance(result, str):
                return result

            # LLM wants to call a tool
            assert isinstance(result, ToolCallResult)
            handler = self._tool_handlers.get(result.tool_name)
            if handler is None:
                # Unknown tool — tell the LLM and let it retry
                working_messages.append({
                    "role": "assistant",
                    "content": f"[Attempted to call unknown tool: {result.tool_name}]",
                })
                continue

            # Execute the tool
            tool_output = await handler(context=context, **result.arguments)

            # Append the exchange so the LLM sees what happened
            working_messages.append({
                "role": "assistant",
                "content": f"[Tool call: {result.tool_name}({result.arguments})]",
            })
            working_messages.append({
                "role": "user",
                "content": f"[Tool result: {tool_output}]",
            })

        # Exhausted iterations — ask LLM for a final text answer
        working_messages.append({
            "role": "user",
            "content": "Please provide your final response to the user based on the information gathered.",
        })
        return await self.llm.generate(working_messages, temperature=0.7)

    # ------------------------------------------------------------------
    # Response construction
    # ------------------------------------------------------------------

    def _make_response(self, content: str, context: dict) -> AgentResponse:
        """Wrap raw LLM output into a structured AgentResponse.

        Subclasses can override to add suggested_actions, handoff logic, etc.
        """
        return AgentResponse(
            content=content,
            agent_name=self.name,
            agent_type=self._agent_type(),
        )

    def _agent_type(self) -> str:
        """Return a human-readable type for this agent."""
        return "general"
