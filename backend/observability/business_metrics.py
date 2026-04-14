"""Business metrics — approval rate, risk distribution, conversion funnel."""

from collections import defaultdict
from threading import Lock

_lock = Lock()
_decisions: list[str] = []
_categories: list[str] = []
_funnel: dict[str, int] = defaultdict(int)


def record_scoring(decision: str, risk_category: str) -> None:
    with _lock:
        _decisions.append(decision)
        _categories.append(risk_category)
        _funnel["scoring"] += 1
        if decision == "APPROVE":
            _funnel["approved"] += 1


def record_funnel_event(event: str) -> None:
    """Events: onboarding_start, scoring, approved, account_created."""
    with _lock:
        _funnel[event] += 1


def get_business_metrics() -> dict:
    with _lock:
        total = len(_decisions)
        approved = _decisions.count("APPROVE") if total else 0
        cat_counts = {c: _categories.count(c) for c in ("LOW", "MEDIUM", "HIGH")}
        return {
            "approval_rate": round(approved / total, 3) if total else 0,
            "total_scored": total,
            "risk_distribution": cat_counts,
            "funnel": dict(_funnel),
        }
