"""LLM Provider — abstract base class for unified LLM interface."""

from abc import ABC, abstractmethod
from typing import AsyncIterator

from pydantic import BaseModel


class ToolDefinition(BaseModel):
    """A tool the LLM can call."""

    name: str
    description: str
    parameters: dict  # JSON Schema for the tool's parameters


class ToolCallResult(BaseModel):
    """Result from an LLM tool call."""

    tool_name: str
    arguments: dict


class LLMProvider(ABC):
    """Unified interface for LLM providers (Ollama local, AWS Bedrock)."""

    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
    ) -> str:
        """Generate a complete response from the LLM.

        Args:
            messages: List of {"role": "user"|"assistant"|"system", "content": "..."}.
            tools: Optional tool definitions the model may call.
            temperature: Sampling temperature.

        Returns:
            The assistant's text response.
        """
        ...

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """Stream response tokens from the LLM.

        Yields text chunks as they arrive.
        """
        ...

    @abstractmethod
    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[ToolDefinition],
        temperature: float = 0.7,
    ) -> ToolCallResult | str:
        """Generate a response that may include a tool call.

        Returns either a ToolCallResult (if the model invoked a tool)
        or a plain string response.
        """
        ...
