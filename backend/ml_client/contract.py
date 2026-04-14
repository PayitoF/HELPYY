"""ML API Contract — aligned with MLRepo real API.

The MLRepo exposes a Logistic Regression model trained on 12 selected features.
This contract defines endpoints, thresholds, and feature specs.

Endpoints:
    POST /risk-score   — Credit scoring (probability_of_default + decision)
    GET  /health       — Service health + model loaded status
    GET  /model-info   — Model metadata

Thresholds (from MLRepo/src/api/predictor.py):
    risk_category:  < 0.30 → LOW,  < 0.60 → MEDIUM,  >= 0.60 → HIGH
    decision:       < 0.40 → APPROVE, < 0.65 → REVIEW, >= 0.65 → REJECT
"""

# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

ENDPOINTS = {
    "risk_score": {
        "method": "POST",
        "path": "/risk-score",
        "description": "Score a client for credit eligibility.",
        "request_schema": "RiskRequest",
        "response_schema": "RiskResponse",
    },
    "health": {
        "method": "GET",
        "path": "/health",
        "description": "Service health check.",
        "response_schema": "HealthResponse",
    },
    "model_info": {
        "method": "GET",
        "path": "/model-info",
        "description": "Model metadata and top features.",
        "response_schema": "ModelInfoResponse",
    },
}

# --------------------------------------------------------------------------
# Risk category thresholds
# --------------------------------------------------------------------------

RISK_CATEGORY_THRESHOLDS = {
    "LOW": (0.0, 0.30),
    "MEDIUM": (0.30, 0.60),
    "HIGH": (0.60, 1.0),
}

# --------------------------------------------------------------------------
# Decision thresholds
# --------------------------------------------------------------------------

DECISION_THRESHOLDS = {
    "APPROVE": (0.0, 0.40),
    "REVIEW": (0.40, 0.65),
    "REJECT": (0.65, 1.0),
}

# --------------------------------------------------------------------------
# Selected training features (from config.ini)
# --------------------------------------------------------------------------

SELECTED_FEATURES = [
    "declared_income",
    "is_banked",
    "employment_type",
    "age",
    "city_type",
    "total_sessions",
    "pct_conversion",
    "tx_income_pct",
    "payments_count",
    "on_time_rate",
    "overdue_rate",
    "avg_decision_score",
]

# --------------------------------------------------------------------------
# Top features by importance (from feature_importance.json)
# --------------------------------------------------------------------------

TOP_FEATURES = [
    "on_time_rate",
    "is_banked",
    "pct_conversion",
    "city_type_rural",
    "overdue_rate",
]

# --------------------------------------------------------------------------
# Product limits (business rules applied by our platform, not the ML API)
# --------------------------------------------------------------------------

PRODUCT_LIMITS = {
    "nano": {"min_amount": 100_000, "max_amount": 500_000},
    "micro": {"min_amount": 500_000, "max_amount": 2_000_000},
}
