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
    Path("MLRepo/models/logistic_regression/selected/runs/2026-04-15_115456"),
    Path(__file__).resolve().parent.parent.parent / "MLRepo/models/logistic_regression/selected/runs/2026-04-15_115456",
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

    import sys
    # The model.pkl was pickled with MLRepo/src in the path
    mlrepo_root = model_dir.parent.parent.parent.parent.parent
    if str(mlrepo_root) not in sys.path:
        sys.path.insert(0, str(mlrepo_root))

    import joblib
    _pipeline = joblib.load(model_dir / "model.pkl")

    sf_path = model_dir / "selected_features.json"
    if sf_path.exists():
        _selected_features = json.loads(sf_path.read_text())
    logger.info("ML model loaded from %s", model_dir)
    return True


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
    """Fallback when model.pkl is not available."""
    import math
    income = data.get("declared_income", 1_000_000)
    income_norm = min(income / 3_000_000, 1.0)
    logit = -0.5
    logit += -0.54 * data.get("on_time_rate", 0.5)
    logit += -0.35 * data.get("is_banked", 1)
    logit += -0.31 * data.get("pct_conversion", 0.0)
    logit += 0.24 * (1.0 if data.get("city_type") == "rural" else 0.0)
    logit += 0.20 * data.get("overdue_rate", 0.0)
    logit += -0.15 * income_norm
    p = 1.0 / (1.0 + math.exp(-logit))
    return {
        "probability_of_default": round(p, 6),
        "risk_category": "LOW" if p < 0.30 else "MEDIUM" if p < 0.60 else "HIGH",
        "decision": "APPROVE" if p < 0.40 else "REVIEW" if p < 0.65 else "REJECT",
        "top_features": ["on_time_rate", "is_banked", "pct_conversion"],
    }
