"""Lambda handler — serves the ML model via Function URL or API Gateway.

Mirrors the MLRepo API contract:
  POST /risk-score → { probability_of_default, risk_category, decision, top_features }
  GET  /health     → { status, model_loaded, model_path }
"""

import json
import os
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Load model at cold start
_pipeline = None
_selected_features = []


def _load():
    global _pipeline, _selected_features
    import joblib
    model_path = os.path.join(os.environ.get("LAMBDA_TASK_ROOT", ""), "model", "model.pkl")
    _pipeline = joblib.load(model_path)

    sf_path = os.path.join(os.environ.get("LAMBDA_TASK_ROOT", ""), "model", "selected_features.json")
    if os.path.exists(sf_path):
        _selected_features = json.loads(open(sf_path).read()).get("selected_features", [])
    logger.info("Model loaded: %s", model_path)


_load()


def handler(event, context):
    """Handle Lambda Function URL or ALB/API Gateway requests."""
    # Parse path and method
    path = event.get("rawPath", event.get("path", "/"))
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")

    if path == "/health" or path == "/":
        return _response(200, {
            "status": "ok",
            "model_loaded": _pipeline is not None,
            "model_path": "lambda://model/model.pkl",
        })

    if path == "/risk-score" and method == "POST":
        try:
            body = json.loads(event.get("body", "{}"))
            return _predict(body)
        except Exception as e:
            logger.exception("Prediction error")
            return _response(500, {"error": str(e)})

    if path == "/model-info":
        return _response(200, {
            "model_name": "logistic_regression",
            "training_mode": "selected",
            "model_path": "lambda://model/model.pkl",
            "selected_training_features": _selected_features,
            "top_features": _selected_features[:5],
        })

    return _response(404, {"error": "Not found"})


def _predict(data: dict) -> dict:
    import pandas as pd
    df = pd.DataFrame([data])
    p = float(_pipeline.predict_proba(df)[0, 1])

    risk_category = "LOW" if p < 0.30 else "MEDIUM" if p < 0.60 else "HIGH"
    decision = "APPROVE" if p < 0.40 else "REVIEW" if p < 0.65 else "REJECT"

    return _response(200, {
        "probability_of_default": round(p, 6),
        "risk_category": risk_category,
        "decision": decision,
        "top_features": _selected_features[:5],
    })


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
