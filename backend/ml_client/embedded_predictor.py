"""Embedded ML predictor — loads model.pkl directly, no external service needed.

Used in production (App Runner) where there's no separate ML service.
Falls back to heuristic scoring if model file is not found.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Search paths for the model (repo root or relative to this file)
_MODEL_SEARCH_PATHS = [
    Path(__file__).resolve().parent / "model",
    Path("backend/ml_client/model"),
    Path("MLRepo/models/logistic_regression/selected/runs/2026-04-15_115456"),
]

_pipeline = None
_selected_features = None


def _find_model_dir() -> Path | None:
    for p in _MODEL_SEARCH_PATHS:
        if (p / "model.pkl").exists():
            return p
    return None


def _load_model():
    global _pipeline, _selected_features
    model_dir = _find_model_dir()
    if model_dir is None:
        logger.warning("model.pkl not found — using heuristic scoring")
        return False

    try:
        import joblib
        _pipeline = joblib.load(model_dir / "model.pkl")

        sf_path = model_dir / "selected_features.json"
        if sf_path.exists():
            _selected_features = json.loads(sf_path.read_text())
        logger.info("ML model loaded from %s", model_dir)
        return True
    except Exception as e:
        logger.warning("Failed to load model.pkl: %s — using heuristic", e)
        return False


def predict_embedded(request_data: dict) -> dict:
    """Predict using embedded model. Returns same format as MLRepo API."""
    global _pipeline
    if _pipeline is None:
        if not _load_model():
            return _heuristic_predict(request_data)

    import pandas as pd
    df = pd.DataFrame([request_data])
    p = float(_pipeline.predict_proba(df)[0, 1])

    top = (_selected_features or {}).get("selected_features", [])
    return {
        "probability_of_default": round(p, 6),
        "risk_category": "LOW" if p < 0.30 else "MEDIUM" if p < 0.60 else "HIGH",
        "decision": "APPROVE" if p < 0.40 else "REVIEW" if p < 0.65 else "REJECT",
        "top_features": top[:5],
    }


def _heuristic_predict(data: dict) -> dict:
    """Fallback when model.pkl is not available.

    Calibrated so new users (no history) with low income get REVIEW/REJECT.
    Thresholds: APPROVE < 0.40, REVIEW < 0.65, REJECT >= 0.65
    """
    import math
    income = data.get("declared_income", 1_000_000)
    income_norm = min(income / 3_000_000, 1.0)

    # Start with high base risk for new users
    logit = 0.8

    # Income is the strongest factor for new users
    logit += -1.5 * income_norm

    # Payment history (new users have 0.5 default = neutral)
    on_time = data.get("on_time_rate", 0.5)
    logit += -2.0 * (on_time - 0.5)  # only helps if above 0.5

    # Banking status
    logit += -0.3 * data.get("is_banked", 0)

    # Digital engagement
    logit += -0.5 * data.get("pct_conversion", 0.0)

    # Risk factors
    logit += 0.4 * (1.0 if data.get("city_type") == "rural" else 0.0)
    logit += 1.0 * data.get("overdue_rate", 0.0)

    # Employment type
    emp = data.get("employment_type", "informal")
    if emp == "formal":
        logit += -0.4
    elif emp == "independent":
        logit += -0.2

    # Age (young = more risk)
    age = data.get("age", 30)
    if age < 25:
        logit += 0.3
    elif age > 40:
        logit += -0.2

    p = 1.0 / (1.0 + math.exp(-logit))
    return {
        "probability_of_default": round(p, 6),
        "risk_category": "LOW" if p < 0.30 else "MEDIUM" if p < 0.60 else "HIGH",
        "decision": "APPROVE" if p < 0.40 else "REVIEW" if p < 0.65 else "REJECT",
        "top_features": ["on_time_rate", "is_banked", "pct_conversion", "declared_income", "overdue_rate"],
    }
