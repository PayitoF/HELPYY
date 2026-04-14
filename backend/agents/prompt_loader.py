"""Prompt loader — loads versioned system prompts from .txt files."""

import os
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def load_prompt(agent_name: str, version: int | None = None) -> str:
    """Load a system prompt for an agent.

    Checks env var {AGENT_NAME}_PROMPT_VERSION first, then falls back to
    the provided version or 1.
    """
    env_key = f"{agent_name.upper()}_PROMPT_VERSION"
    v = int(os.getenv(env_key, version or 1))
    path = _PROMPTS_DIR / f"{agent_name}_v{v}.txt"
    if not path.exists():
        path = _PROMPTS_DIR / f"{agent_name}_v1.txt"
    return path.read_text(encoding="utf-8").strip()
