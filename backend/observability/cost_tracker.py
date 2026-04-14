"""Cost tracker — estimates per-conversation and daily costs."""

import logging
import os
import time
from collections import defaultdict
from threading import Lock

logger = logging.getLogger("observability.cost")

_lock = Lock()
_DAILY_ALERT = float(os.getenv("DAILY_COST_ALERT_USD", "10.0"))

# Pricing (USD) — Bedrock Claude Sonnet
_LLM_INPUT_PER_1K = 0.003
_LLM_OUTPUT_PER_1K = 0.015
_ML_CALL_COST = 0.0001  # SageMaker per invocation estimate
_DDB_WRITE_COST = 0.00000125  # per WCU

# Accumulators
_session_costs: dict[str, float] = defaultdict(float)
_daily_costs: dict[str, float] = defaultdict(float)  # key: YYYY-MM-DD


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def record_llm_cost(session_id: str, tokens_in: int, tokens_out: int) -> None:
    cost = (tokens_in / 1000) * _LLM_INPUT_PER_1K + (tokens_out / 1000) * _LLM_OUTPUT_PER_1K
    with _lock:
        _session_costs[session_id] += cost
        _daily_costs[_today()] += cost
    _check_daily_alert()


def record_ml_cost(session_id: str) -> None:
    with _lock:
        _session_costs[session_id] += _ML_CALL_COST
        _daily_costs[_today()] += _ML_CALL_COST


def record_db_cost(session_id: str, writes: int = 1) -> None:
    cost = writes * _DDB_WRITE_COST
    with _lock:
        _session_costs[session_id] += cost
        _daily_costs[_today()] += cost


def get_cost_report(days: int = 7) -> dict:
    with _lock:
        sorted_days = sorted(_daily_costs.keys(), reverse=True)[:days]
        daily = {d: round(_daily_costs[d], 6) for d in sorted_days}
        total = sum(daily.values())
        return {
            "daily_costs_usd": daily,
            "total_usd": round(total, 6),
            "active_sessions": len(_session_costs),
            "alert_threshold_usd": _DAILY_ALERT,
        }


def _check_daily_alert() -> None:
    today_cost = _daily_costs.get(_today(), 0)
    if today_cost > _DAILY_ALERT:
        logger.warning("COST ALERT: $%.4f today exceeds $%.2f threshold", today_cost, _DAILY_ALERT)
