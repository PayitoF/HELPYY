"""LLM configuration — factory that returns the correct provider."""

import os

from backend.llm.provider import LLMProvider


def get_llm_provider() -> LLMProvider:
    """Factory: returns Ollama (local) or Bedrock (prod) based on LLM_PROVIDER env var."""
    provider = os.getenv("LLM_PROVIDER", "local")
    if provider == "local":
        from backend.llm.ollama_provider import OllamaProvider

        return OllamaProvider()
    elif provider == "bedrock":
        from backend.llm.bedrock_provider import BedrockProvider

        return BedrockProvider()
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: {provider!r}. Use 'local' or 'bedrock'."
        )
