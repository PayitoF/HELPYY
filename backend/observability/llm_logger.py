"""LLM Logger — structured JSON logging for all LLM interactions (no PII)."""

import json
import logging
import time
from typing import Any

logger = logging.getLogger("llm_ops")


def log_llm_call(
    session_id: str,
    agent: str,
    latency_ms: float,
    tokens_in: int = 0,
    tokens_out: int = 0,
    model: str = "",
    prompt_version: int = 1,
    intent: str = "",
    error: str | None = None,
) -> None:
    entry = {
        "ts": time.time(),
        "session_id": session_id,
        "agent": agent,
        "intent": intent,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "latency_ms": round(latency_ms, 1),
        "model": model,
        "prompt_version": prompt_version,
    }
    if error:
        entry["error"] = error
        logger.error(json.dumps(entry, ensure_ascii=False))
    else:
        logger.info(json.dumps(entry, ensure_ascii=False))
