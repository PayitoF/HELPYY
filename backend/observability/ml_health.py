"""ML Health — periodic health check of the ML scoring service."""

import asyncio
import logging
import os
import time

import httpx

logger = logging.getLogger("observability.ml_health")

_CHECK_INTERVAL = int(os.getenv("ML_HEALTH_CHECK_INTERVAL", "30"))
_ML_URL = os.getenv("ML_SERVICE_URL", "http://localhost:8001")
_consecutive_failures = 0
_last_status: dict = {"status": "unknown", "checked_at": 0}


async def check_ml_health() -> dict:
    global _consecutive_failures, _last_status
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{_ML_URL}/health")
            resp.raise_for_status()
            data = resp.json()
        latency = (time.perf_counter() - t0) * 1000
        _consecutive_failures = 0
        _last_status = {
            "status": "healthy",
            "latency_ms": round(latency, 1),
            "model_loaded": data.get("model_loaded", False),
            "checked_at": time.time(),
        }
        logger.info("ML health OK: %.0fms, model_loaded=%s", latency, data.get("model_loaded"))
    except Exception as e:
        _consecutive_failures += 1
        _last_status = {
            "status": "unhealthy",
            "error": str(e),
            "consecutive_failures": _consecutive_failures,
            "checked_at": time.time(),
        }
        if _consecutive_failures >= 3:
            logger.critical("ML service DOWN: %d consecutive failures: %s", _consecutive_failures, e)
        else:
            logger.warning("ML health check failed (%d): %s", _consecutive_failures, e)
    return _last_status


def get_ml_status() -> dict:
    return _last_status


async def start_health_loop() -> None:
    """Background loop — call from FastAPI lifespan."""
    while True:
        await check_ml_health()
        await asyncio.sleep(_CHECK_INTERVAL)
