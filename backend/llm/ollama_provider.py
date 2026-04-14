"""Ollama LLM provider — local development with Gemma 4."""

import asyncio
import json
import logging
import os
from typing import AsyncIterator

import httpx

from backend.llm.provider import LLMProvider, ToolCallResult, ToolDefinition

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_TIMEOUT_SECONDS = 60
_BACKOFF_BASE = 2  # seconds


class OllamaProvider(LLMProvider):
    """LLM provider using Ollama for local development.

    Communicates via httpx async to Ollama's /api/chat endpoint.
    Retry with exponential backoff on transient (5xx / network) failures.
    """

    def __init__(self):
        self.model = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
        self.base_url = os.getenv("OLLAMA_URL", "http://localhost:11434")

    # ------------------------------------------------------------------
    # generate (non-streaming)
    # ------------------------------------------------------------------
    async def generate(
        self,
        messages: list[dict],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
    ) -> str:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if tools:
            payload["tools"] = [_tool_to_ollama(t) for t in tools]

        data = await self._post_with_retry(payload)
        return data["message"]["content"]

    # ------------------------------------------------------------------
    # generate_stream
    # ------------------------------------------------------------------
    async def generate_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(_TIMEOUT_SECONDS)) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if chunk.get("done"):
                        break

    # ------------------------------------------------------------------
    # generate_with_tools
    # ------------------------------------------------------------------
    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        temperature: float = 0.7,
    ) -> ToolCallResult | str:
        # First, try native tool calling.
        try:
            return await self._generate_with_native_tools(messages, tools, temperature)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                # Model doesn't support tools — fall back to prompt-based approach.
                logger.info("Model %s doesn't support native tools, using prompt fallback", self.model)
            else:
                raise

        # Prompt-based fallback: inject tool descriptions into system message
        # and ask the model to respond with JSON when it wants to call a tool.
        return await self._generate_with_prompt_tools(messages, tools, temperature)

    async def _generate_with_native_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        temperature: float,
    ) -> ToolCallResult | str:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
            "tools": [_tool_to_ollama(t) for t in tools],
        }

        data = await self._post_with_retry(payload)
        msg = data["message"]

        tool_calls = msg.get("tool_calls")
        if tool_calls:
            tc = tool_calls[0]
            fn = tc["function"]
            return ToolCallResult(
                tool_name=fn["name"],
                arguments=fn.get("arguments", {}),
            )

        # Model might have embedded a tool call in text
        content = msg.get("content", "")
        parsed = _parse_tool_call_from_text(content, tools)
        if parsed:
            return parsed

        return content

    async def _generate_with_prompt_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        temperature: float,
    ) -> ToolCallResult | str:
        tool_descriptions = "\n".join(
            f'- {t.name}: {t.description}. Parameters: {json.dumps(t.parameters)}'
            for t in tools
        )
        tool_system = (
            "You have access to these tools:\n"
            f"{tool_descriptions}\n\n"
            "If you need to use a tool, respond ONLY with a JSON object like:\n"
            '{"name": "tool_name", "arguments": {"param": "value"}}\n'
            "If you do not need a tool, respond normally in text."
        )

        augmented = list(messages)
        # Prepend or merge with existing system message
        if augmented and augmented[0]["role"] == "system":
            augmented[0] = {
                "role": "system",
                "content": augmented[0]["content"] + "\n\n" + tool_system,
            }
        else:
            augmented.insert(0, {"role": "system", "content": tool_system})

        content = await self.generate(augmented, tools=None, temperature=temperature)

        parsed = _parse_tool_call_from_text(content, tools)
        if parsed:
            return parsed
        return content

    # ------------------------------------------------------------------
    # internal: POST with retry + exponential backoff (only retries 5xx / network)
    # ------------------------------------------------------------------
    async def _post_with_retry(self, payload: dict) -> dict:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(_TIMEOUT_SECONDS)
                ) as client:
                    resp = await client.post(
                        f"{self.base_url}/api/chat",
                        json=payload,
                    )
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as exc:
                # Don't retry client errors (4xx) — they won't self-resolve
                if exc.response.status_code < 500:
                    raise
                last_exc = exc
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc

            wait = _BACKOFF_BASE ** attempt
            logger.warning(
                "Ollama request failed (attempt %d/%d): %s — retrying in %ds",
                attempt + 1,
                _MAX_RETRIES,
                last_exc,
                wait,
            )
            await asyncio.sleep(wait)

        raise ConnectionError(
            f"Ollama request failed after {_MAX_RETRIES} attempts"
        ) from last_exc


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _tool_to_ollama(tool: ToolDefinition) -> dict:
    """Convert a ToolDefinition to Ollama's tool format."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _parse_tool_call_from_text(
    text: str, tools: list[ToolDefinition]
) -> ToolCallResult | None:
    """Best-effort extraction of a tool call from plain text.

    Looks for a JSON block containing a known tool name.
    """
    tool_names = {t.name for t in tools}
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None

    name = obj.get("name") or obj.get("tool") or obj.get("function")
    args = obj.get("arguments") or obj.get("args") or obj.get("parameters") or {}
    if isinstance(name, str) and name in tool_names:
        return ToolCallResult(tool_name=name, arguments=args)
    return None
