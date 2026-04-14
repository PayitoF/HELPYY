"""Metrics — counters and histograms per agent, Prometheus-compatible output."""

import logging
import time
from collections import defaultdict
from threading import Lock

logger = logging.getLogger("observability.metrics")

_lock = Lock()

# Counters
_requests: dict[str, int] = defaultdict(int)
_errors: dict[str, int] = defaultdict(int)
_handoffs: dict[str, int] = defaultdict(int)

# Latency samples (sliding window of last 200 per agent)
_latencies: dict[str, list[float]] = defaultdict(list)
_MAX_SAMPLES = 200

# Error rate window (timestamps of last 5 min)
_error_ts: dict[str, list[float]] = defaultdict(list)
_request_ts: dict[str, list[float]] = defaultdict(list)
_WINDOW = 300  # 5 min


def record_request(agent: str, latency_ms: float, error: bool = False) -> None:
    now = time.time()
    with _lock:
        _requests[agent] += 1
        _request_ts[agent].append(now)
        _latencies[agent].append(latency_ms)
        if len(_latencies[agent]) > _MAX_SAMPLES:
            _latencies[agent] = _latencies[agent][-_MAX_SAMPLES:]
        if error:
            _errors[agent] += 1
            _error_ts[agent].append(now)

        # Prune old timestamps
        cutoff = now - _WINDOW
        _request_ts[agent] = [t for t in _request_ts[agent] if t > cutoff]
        _error_ts[agent] = [t for t in _error_ts[agent] if t > cutoff]

    # Alerts
    _check_alerts(agent, latency_ms, error)


def record_handoff(from_agent: str, to_agent: str) -> None:
    with _lock:
        _handoffs[f"{from_agent}->{to_agent}"] += 1


def get_metrics() -> dict:
    with _lock:
        agents = set(_requests.keys())
        result = {"agents": {}}
        for a in sorted(agents):
            lats = _latencies.get(a, [])
            slats = sorted(lats)
            result["agents"][a] = {
                "requests_total": _requests[a],
                "errors_total": _errors[a],
                "latency_p50_ms": slats[len(slats) // 2] if slats else 0,
                "latency_p99_ms": slats[int(len(slats) * 0.99)] if slats else 0,
                "avg_tokens": 0,
            }
        result["handoffs"] = dict(_handoffs)
        return result


def get_prometheus() -> str:
    m = get_metrics()
    lines = []
    for a, d in m.get("agents", {}).items():
        lines.append(f'helpyy_requests_total{{agent="{a}"}} {d["requests_total"]}')
        lines.append(f'helpyy_errors_total{{agent="{a}"}} {d["errors_total"]}')
        lines.append(f'helpyy_latency_p50_ms{{agent="{a}"}} {d["latency_p50_ms"]:.1f}')
        lines.append(f'helpyy_latency_p99_ms{{agent="{a}"}} {d["latency_p99_ms"]:.1f}')
    for h, c in m.get("handoffs", {}).items():
        lines.append(f'helpyy_handoffs_total{{route="{h}"}} {c}')
    return "\n".join(lines) + "\n"


def _check_alerts(agent: str, latency_ms: float, error: bool) -> None:
    # Latency alert
    lats = _latencies.get(agent, [])
    if len(lats) >= 10:
        p99 = sorted(lats)[int(len(lats) * 0.99)]
        if p99 > 5000:
            logger.warning("ALERT: %s P99 latency %.0fms > 5000ms", agent, p99)

    # Error rate alert
    now = time.time()
    cutoff = now - _WINDOW
    recent_req = len([t for t in _request_ts.get(agent, []) if t > cutoff])
    recent_err = len([t for t in _error_ts.get(agent, []) if t > cutoff])
    if recent_req >= 20 and recent_err / recent_req > 0.05:
        logger.critical("ALERT: %s error rate %.1f%% > 5%% (window 5min)", agent, recent_err / recent_req * 100)
