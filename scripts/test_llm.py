#!/usr/bin/env python3
"""E2E verification of the LLM Gateway against local Ollama.

Sends a simple message, streams the response, and prints a report with:
model, first-token latency, total latency, and token count.
"""

import asyncio
import os
import time

os.environ.setdefault("LLM_PROVIDER", "local")

from backend.llm import get_llm_provider, ToolDefinition


async def main():
    provider = get_llm_provider()

    messages = [
        {
            "role": "system",
            "content": (
                "Eres Helpyy Hand, asistente financiero de BBVA Colombia. "
                "Responde en maximo 2 frases cortas."
            ),
        },
        {"role": "user", "content": "Hola, quiero abrir una cuenta de ahorros"},
    ]

    # ---- streaming test ----
    t0 = time.perf_counter()
    first_token_time = None
    chunks: list[str] = []

    async for token in provider.generate_stream(messages, temperature=0.7):
        if first_token_time is None:
            first_token_time = time.perf_counter() - t0
        chunks.append(token)

    total_time = time.perf_counter() - t0
    text = "".join(chunks)
    token_count = len(chunks)

    # ---- tool-calling test ----
    tools = [
        ToolDefinition(
            name="check_credit_score",
            description="Consulta el score crediticio de un usuario por su cedula",
            parameters={
                "type": "object",
                "properties": {
                    "cedula": {"type": "string", "description": "Cedula del usuario"},
                },
                "required": ["cedula"],
            },
        ),
    ]
    tool_msgs = [
        {
            "role": "system",
            "content": "Usa check_credit_score cuando el usuario pida su puntaje.",
        },
        {"role": "user", "content": "Mi cedula es 1234567890, quiero mi puntaje"},
    ]

    t1 = time.perf_counter()
    tool_result = await provider.generate_with_tools(tool_msgs, tools, temperature=0.3)
    tool_time = time.perf_counter() - t1

    # ---- report ----
    print()
    print("=" * 60)
    print("  REPORTE — LLM Gateway E2E")
    print("=" * 60)
    print(f"  Modelo:            {provider.model}")
    print(f"  Provider:          {type(provider).__name__}")
    print(f"  URL:               {provider.base_url}")
    print("-" * 60)
    print(f"  Primer token:      {first_token_time:.3f}s")
    print(f"  Tiempo total:      {total_time:.3f}s")
    print(f"  Tokens generados:  {token_count}")
    tps = token_count / total_time if total_time > 0 else 0
    print(f"  Tokens/segundo:    {tps:.1f}")
    print("-" * 60)
    print(f"  Respuesta:")
    print(f"    {text}")
    print("-" * 60)
    print(f"  Tool calling:      {'OK' if hasattr(tool_result, 'tool_name') else 'text fallback'}")
    print(f"    Resultado:       {tool_result}")
    print(f"    Tiempo:          {tool_time:.3f}s")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
