"""ML API Contract — inferred from MLRepo Risk Generating Process analysis.

The MLRepo does NOT contain a trained ML model. It is a synthetic data generation
pipeline with a hand-crafted Risk Generating Process (RGP) based on weighted linear
combinations + logistic sigmoid. This contract defines the API that the ML team
should expose for integration with the agent platform.

Endpoints:
    POST /api/ml/predict              — Credit scoring + eligibility
    GET  /api/ml/score-history/{id}   — Historical scores for a client
    GET  /api/ml/features-spec        — Feature specification (names, types, ranges)
    GET  /api/ml/model-info           — Model metadata and performance metrics

Risk Generating Process (3 stages):
    1. base_risk_score = weighted(f_income, f_emp, f_banked, f_age, f_city, f_edu)
       Weights: income(1.1), employment(1.0), banked(0.8), age(0.7), education(0.5), city(0.4)

    2. risk_index = weighted(on_time_rate, overdue_rate, rejection_rate,
                             base_risk_score, pct_conversion, income, is_banked)
       Weights: on_time(0.6), overdue(0.4), rejection(0.3), base_risk(0.25),
                conversion(0.2), income(0.2), banked(0.2)

    3. p_default = sigmoid(intercept + 4.0*risk_index + 2.0*(1-on_time_rate)
                   + 1.5*overdue_rate + 1.8*rejection_rate - 0.8*pct_conversion)
       Default base_rate = 0.15

Score bands:
    p_default < 0.20 → low_risk
    p_default < 0.50 → medium_risk
    p_default >= 0.50 → high_risk

Product types: nano (100K-500K COP), micro (500K-2M COP), reload
"""

# --------------------------------------------------------------------------
# Endpoint specifications
# --------------------------------------------------------------------------

ENDPOINTS = {
    "predict": {
        "method": "POST",
        "path": "/api/ml/predict",
        "description": "Score a client for nano/micro credit eligibility.",
        "request_schema": "PredictRequest",
        "response_schema": "CreditPrediction",
        "timeout_ms": 5000,
        "retry_on_5xx": True,
    },
    "score_history": {
        "method": "GET",
        "path": "/api/ml/score-history/{client_id}",
        "description": "Retrieve historical credit scores for a client.",
        "response_schema": "list[ScoreEntry]",
        "timeout_ms": 3000,
        "retry_on_5xx": True,
    },
    "features_spec": {
        "method": "GET",
        "path": "/api/ml/features-spec",
        "description": "Feature specification: names, types, ranges, allowed values.",
        "response_schema": "list[FeatureSpec]",
        "timeout_ms": 2000,
        "retry_on_5xx": False,
    },
    "model_info": {
        "method": "GET",
        "path": "/api/ml/model-info",
        "description": "Model metadata, version, and performance metrics.",
        "response_schema": "ModelInfo",
        "timeout_ms": 2000,
        "retry_on_5xx": False,
    },
}

# --------------------------------------------------------------------------
# Risk index weights (from risk_feature_builder.py)
# --------------------------------------------------------------------------

RISK_INDEX_WEIGHTS = {
    "on_time_rate": 0.6,       # (1 - on_time_rate) — higher rate = lower risk
    "overdue_rate": 0.4,       # direct — higher = more risk
    "rejection_rate": 0.3,     # direct — higher = more risk
    "base_risk_score": 0.25,   # demographic composite
    "pct_conversion": 0.2,     # (1 - pct_conversion) — higher = lower risk
    "declared_income": 0.2,    # 1/(1+income) — higher income = lower risk
    "is_banked": 0.2,          # (1 - is_banked) — banked = lower risk
}

# --------------------------------------------------------------------------
# p_default logit coefficients (from target_builder.py)
# --------------------------------------------------------------------------

P_DEFAULT_COEFFICIENTS = {
    "risk_index": 4.0,
    "on_time_rate_inv": 2.0,   # coefficient on (1 - on_time_rate)
    "overdue_rate": 1.5,
    "rejection_rate": 1.8,
    "pct_conversion": -0.8,    # protective — negative coefficient
}

DEFAULT_BASE_RATE = 0.15  # intercept = -log(1/base_rate - 1)

# --------------------------------------------------------------------------
# base_risk_score factor weights (from clients_generator.py)
# --------------------------------------------------------------------------

BASE_RISK_WEIGHTS = {
    "f_income": 1.1,
    "f_employment": 1.0,
    "f_banked": 0.8,
    "f_age": 0.7,
    "f_education": 0.5,
    "f_city": 0.4,
}

# --------------------------------------------------------------------------
# Score band thresholds
# --------------------------------------------------------------------------

SCORE_BANDS = {
    "low_risk": (0.0, 0.20),
    "medium_risk": (0.20, 0.50),
    "high_risk": (0.50, 1.0),
}

# --------------------------------------------------------------------------
# Product limits (inferred from loan_applications_generator.py)
# --------------------------------------------------------------------------

PRODUCT_LIMITS = {
    "nano": {"min_amount": 100_000, "max_amount": 500_000},
    "micro": {"min_amount": 500_000, "max_amount": 2_000_000},
    "reload": {"min_amount": 50_000, "max_amount": 1_000_000},
}

# --------------------------------------------------------------------------
# Feature ranges (from clients_generator.py distributions)
# --------------------------------------------------------------------------

FEATURE_RANGES = {
    "declared_income": {"min": 300_000, "max": 15_000_000, "type": "float", "unit": "COP"},
    "employment_type": {"allowed": ["informal", "formal", "independent"], "type": "str"},
    "is_banked": {"type": "bool"},
    "age": {"min": 18, "max": 74, "type": "int"},
    "city_type": {"allowed": ["urban", "rural"], "type": "str"},
    "education_level": {"allowed": ["none", "primary", "secondary", "technical", "university"], "type": "str"},
    "household_size": {"min": 1, "max": 7, "type": "int"},
    "on_time_rate": {"min": 0.0, "max": 1.0, "type": "float", "optional": True},
    "overdue_rate": {"min": 0.0, "max": 1.0, "type": "float", "optional": True},
    "rejection_rate": {"min": 0.0, "max": 1.0, "type": "float", "optional": True},
    "pct_conversion": {"min": 0.0, "max": 1.0, "type": "float", "optional": True},
    "total_sessions": {"min": 0, "max": 100, "type": "int", "optional": True},
    "tx_count": {"min": 0, "max": 200, "type": "int", "optional": True},
    "apps_count": {"min": 0, "max": 20, "type": "int", "optional": True},
}

# --------------------------------------------------------------------------
# Error codes
# --------------------------------------------------------------------------

ERROR_CODES = {
    "INVALID_FEATURES": {"status": 422, "description": "Feature values out of range or missing required fields"},
    "CLIENT_NOT_FOUND": {"status": 404, "description": "Client ID not found in score history"},
    "MODEL_UNAVAILABLE": {"status": 503, "description": "Model service temporarily unavailable"},
    "INTERNAL_ERROR": {"status": 500, "description": "Unexpected internal error"},
}
