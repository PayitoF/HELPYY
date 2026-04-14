"""Mock ML service — mirrors MLRepo/src/api/app.py endpoints.

Replicates the real API contract so the agent platform can develop locally
without the ML team's service running.

Endpoints (same as MLRepo):
    POST /risk-score  → RiskResponse
    GET  /health      → HealthResponse
    GET  /model-info  → ModelInfoResponse

Thresholds match MLRepo/src/api/predictor.py:
    risk_category:  < 0.30 → LOW,  < 0.60 → MEDIUM,  >= 0.60 → HIGH
    decision:       < 0.40 → APPROVE, < 0.65 → REVIEW, >= 0.65 → REJECT

Run standalone:
    uvicorn backend.ml_client.mock_server:app --host 0.0.0.0 --port 8001 --reload
"""

import math

from fastapi import FastAPI

from backend.ml_client.schemas import (
    HealthResponse,
    ModelInfoResponse,
    RiskRequest,
    RiskResponse,
)

app = FastAPI(title="ML Mock Service — HelpyHand", version="2.0.0")


# -----------------------------------------------------------------------
# GET /health
# -----------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        model_loaded=True,
        model_path="mock://logistic_regression/selected",
    )


# -----------------------------------------------------------------------
# GET /
# -----------------------------------------------------------------------

@app.get("/")
async def root():
    return {
        "message": "HelpyHand Risk Scoring API (mock) is running",
        "docs": "/docs",
        "health": "/health",
        "model_info": "/model-info",
    }


# -----------------------------------------------------------------------
# GET /model-info
# -----------------------------------------------------------------------

@app.get("/model-info", response_model=ModelInfoResponse)
async def model_info():
    return ModelInfoResponse(
        model_name="logistic_regression",
        training_mode="selected",
        model_path="mock://logistic_regression/selected",
        run_dir="mock://runs/2026-04-10_163938",
        selected_training_features=[
            "declared_income", "is_banked", "employment_type", "age",
            "city_type", "total_sessions", "pct_conversion", "tx_income_pct",
            "payments_count", "on_time_rate", "overdue_rate", "avg_decision_score",
        ],
        top_features=[
            "on_time_rate", "is_banked", "pct_conversion",
            "city_type_rural", "overdue_rate",
        ],
    )


# -----------------------------------------------------------------------
# POST /risk-score
# -----------------------------------------------------------------------

@app.post("/risk-score", response_model=RiskResponse)
async def risk_score(payload: RiskRequest):
    p = _compute_probability(payload)
    risk_category = _resolve_risk_category(p)
    decision = _resolve_decision(p)

    return RiskResponse(
        probability_of_default=round(p, 6),
        risk_category=risk_category,
        decision=decision,
        top_features=["on_time_rate", "is_banked", "pct_conversion", "city_type_rural", "overdue_rate"],
    )


# -----------------------------------------------------------------------
# Mock scoring logic — approximates the real logistic regression
# -----------------------------------------------------------------------

def _compute_probability(req: RiskRequest) -> float:
    """Heuristic that mimics the trained logistic regression.

    Uses the real top-5 feature coefficients from feature_importance.json:
        on_time_rate:    -0.5417  (higher → lower risk)
        is_banked:       -0.3456  (banked → lower risk)
        pct_conversion:  -0.3063  (higher → lower risk)
        city_type_rural:  0.2376  (rural → higher risk)
        overdue_rate:     0.1970  (higher → higher risk)
    """
    logit = -0.5  # intercept (calibrated to ~38% base default rate)

    logit += -0.54 * req.on_time_rate
    logit += -0.35 * req.is_banked
    logit += -0.31 * req.pct_conversion
    logit += 0.24 * (1.0 if req.city_type == "rural" else 0.0)
    logit += 0.20 * req.overdue_rate

    # Secondary features (smaller effect)
    income_norm = min(req.declared_income / 5_000_000, 1.0)
    logit += -0.15 * income_norm
    logit += -0.10 * req.avg_decision_score
    logit += -0.05 * min(req.total_sessions / 20.0, 1.0)

    return 1.0 / (1.0 + math.exp(-logit))


def _resolve_risk_category(p: float) -> str:
    if p < 0.30:
        return "LOW"
    if p < 0.60:
        return "MEDIUM"
    return "HIGH"


def _resolve_decision(p: float) -> str:
    if p < 0.40:
        return "APPROVE"
    if p < 0.65:
        return "REVIEW"
    return "REJECT"
