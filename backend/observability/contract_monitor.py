"""Contract monitor — periodic validation of ML service contract."""

import asyncio
import logging
import os
import time

import httpx

logger = logging.getLogger("observability.contract")

_ML_URL = os.getenv("ML_SERVICE_URL", "http://localhost:8001")
_last_check: dict = {"status": "pending", "checked_at": 0, "tests": []}

# Minimal contract test payload
_TEST_PAYLOAD = {
    "declared_income": 3_000_000, "is_banked": 1, "employment_type": "formal",
    "age": 35, "city_type": "urban", "total_sessions": 10, "pct_conversion": 0.6,
    "tx_income_pct": 0.5, "payments_count": 15, "on_time_rate": 0.9,
    "overdue_rate": 0.05, "avg_decision_score": 0.8,
}


async def run_contract_check() -> dict:
    global _last_check
    results = []

    async with httpx.AsyncClient(base_url=_ML_URL, timeout=10) as client:
        # Test 1: /risk-score returns valid schema
        try:
            r = await client.post("/risk-score", json=_TEST_PAYLOAD)
            data = r.json()
            ok = (r.status_code == 200
                  and "probability_of_default" in data
                  and "risk_category" in data
                  and "decision" in data
                  and "top_features" in data)
            results.append({"test": "risk_score_schema", "passed": ok})
        except Exception as e:
            results.append({"test": "risk_score_schema", "passed": False, "error": str(e)})

        # Test 2: /health returns ok
        try:
            r = await client.get("/health")
            ok = r.status_code == 200 and r.json().get("status") == "ok"
            results.append({"test": "health", "passed": ok})
        except Exception as e:
            results.append({"test": "health", "passed": False, "error": str(e)})

        # Test 3: /model-info returns valid schema
        try:
            r = await client.get("/model-info")
            data = r.json()
            ok = r.status_code == 200 and "model_name" in data and "top_features" in data
            results.append({"test": "model_info_schema", "passed": ok})
        except Exception as e:
            results.append({"test": "model_info_schema", "passed": False, "error": str(e)})

        # Test 4: thresholds consistency
        try:
            r = await client.post("/risk-score", json=_TEST_PAYLOAD)
            data = r.json()
            p = data["probability_of_default"]
            cat_ok = (p < 0.30 and data["risk_category"] == "LOW") or \
                     (0.30 <= p < 0.60 and data["risk_category"] == "MEDIUM") or \
                     (p >= 0.60 and data["risk_category"] == "HIGH")
            results.append({"test": "threshold_consistency", "passed": cat_ok})
        except Exception as e:
            results.append({"test": "threshold_consistency", "passed": False, "error": str(e)})

    all_passed = all(r["passed"] for r in results)
    _last_check = {
        "status": "pass" if all_passed else "fail",
        "checked_at": time.time(),
        "tests": results,
    }

    if not all_passed:
        failed = [r["test"] for r in results if not r["passed"]]
        logger.critical("CONTRACT VIOLATION: %s", failed)
    else:
        logger.info("Contract check passed: %d tests", len(results))

    return _last_check


def get_contract_status() -> dict:
    return _last_check


async def start_contract_loop(interval_hours: float = 1.0) -> None:
    while True:
        await run_contract_check()
        await asyncio.sleep(interval_hours * 3600)
