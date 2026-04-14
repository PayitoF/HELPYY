"""AWS Bedrock LLM provider — production with Claude."""

import json
import logging
import os
from typing import AsyncIterator

from backend.llm.provider import LLMProvider, ToolCallResult, ToolDefinition

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 2


class BedrockProvider(LLMProvider):
    """LLM provider using AWS Bedrock (Claude) for staging/production.

    Uses the Converse API for text, streaming, and tool use.
    Runs boto3 calls in a thread executor so the async interface stays non-blocking.
    """

    def __init__(self):
        self.model_id = os.getenv(
            "BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-20250514-v1:0"
        )
        self.region = os.getenv("AWS_REGION", "us-east-1")

        import boto3

        self._client = boto3.client(
            "bedrock-runtime", region_name=self.region
        )

    # ------------------------------------------------------------------
    # generate (non-streaming)
    # ------------------------------------------------------------------
    async def generate(
        self,
        messages: list[dict],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
    ) -> str:
        system_prompt, converse_msgs = _split_system(messages)
        kwargs = _build_converse_kwargs(
            self.model_id, system_prompt, converse_msgs, tools, temperature
        )

        response = await self._call_with_retry("converse", kwargs)
        return _extract_text(response)

    # ------------------------------------------------------------------
    # generate_stream
    # ------------------------------------------------------------------
    async def generate_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        system_prompt, converse_msgs = _split_system(messages)
        kwargs = _build_converse_kwargs(
            self.model_id, system_prompt, converse_msgs, None, temperature
        )

        import asyncio

        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, lambda: self._client.converse_stream(**kwargs)
        )

        stream = response.get("stream")
        if stream is None:
            return

        for event in stream:
            delta = event.get("contentBlockDelta", {}).get("delta", {})
            text = delta.get("text", "")
            if text:
                yield text

    # ------------------------------------------------------------------
    # generate_with_tools
    # ------------------------------------------------------------------
    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        temperature: float = 0.7,
    ) -> ToolCallResult | str:
        system_prompt, converse_msgs = _split_system(messages)
        kwargs = _build_converse_kwargs(
            self.model_id, system_prompt, converse_msgs, tools, temperature
        )

        response = await self._call_with_retry("converse", kwargs)

        # Check for tool use in the response
        output = response.get("output", {})
        message = output.get("message", {})
        for block in message.get("content", []):
            if "toolUse" in block:
                tu = block["toolUse"]
                return ToolCallResult(
                    tool_name=tu["name"],
                    arguments=tu.get("input", {}),
                )

        return _extract_text(response)

    # ------------------------------------------------------------------
    # internal: retry with backoff
    # ------------------------------------------------------------------
    async def _call_with_retry(self, method_name: str, kwargs: dict) -> dict:
        import asyncio
        from botocore.exceptions import ClientError

        loop = asyncio.get_running_loop()
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                method = getattr(self._client, method_name)
                return await loop.run_in_executor(None, lambda: method(**kwargs))
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code in ("ThrottlingException", "ModelTimeoutException", "ServiceUnavailableException"):
                    last_exc = exc
                    wait = _BACKOFF_BASE ** attempt
                    logger.warning(
                        "Bedrock %s failed (attempt %d/%d): %s — retrying in %ds",
                        method_name,
                        attempt + 1,
                        _MAX_RETRIES,
                        code,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise

        raise ConnectionError(
            f"Bedrock {method_name} failed after {_MAX_RETRIES} attempts"
        ) from last_exc


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _split_system(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Separate system message from conversation messages.

    Returns (system_prompt, converse_messages) where converse_messages
    are in the Bedrock Converse API format.
    """
    system_prompt = None
    converse_msgs = []
    for msg in messages:
        if msg["role"] == "system":
            system_prompt = msg["content"]
        else:
            converse_msgs.append({
                "role": msg["role"],
                "content": [{"text": msg["content"]}],
            })
    return system_prompt, converse_msgs


def _build_converse_kwargs(
    model_id: str,
    system_prompt: str | None,
    converse_msgs: list[dict],
    tools: list[ToolDefinition] | None,
    temperature: float,
) -> dict:
    """Build kwargs dict for bedrock converse / converse_stream."""
    kwargs: dict = {
        "modelId": model_id,
        "messages": converse_msgs,
        "inferenceConfig": {"temperature": temperature, "maxTokens": 2048},
    }
    if system_prompt:
        kwargs["system"] = [{"text": system_prompt}]
    if tools:
        kwargs["toolConfig"] = {
            "tools": [
                {
                    "toolSpec": {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": {"json": t.parameters},
                    }
                }
                for t in tools
            ]
        }
    return kwargs


def _extract_text(response: dict) -> str:
    """Extract assistant text from a Converse API response."""
    output = response.get("output", {})
    message = output.get("message", {})
    parts = []
    for block in message.get("content", []):
        if "text" in block:
            parts.append(block["text"])
    return "".join(parts)
