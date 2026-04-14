
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import joblib
import pandas as pd

from src.api.schemas import RiskRequest


DEFAULT_MODEL_PATH = Path(
    os.getenv(
        "MODEL_PATH",
        "models/logistic_regression/selected/runs/2026-04-10_163938/model.pkl",
    )
)

DEFAULT_MODEL_LOGS_PATH = Path(
    os.getenv(
        "MODEL_LOGS_PATH",
        "models/logistic_regression/selected/runs/2026-04-10_163938/model_logs.json",
    )
)

DEFAULT_SELECTED_FEATURES_PATH = Path(
    os.getenv(
        "SELECTED_FEATURES_PATH",
        "models/logistic_regression/selected/runs/2026-04-10_163938/selected_features.json",
    )
)


class PredictionService:
    def __init__(
        self,
        model_path: Path = DEFAULT_MODEL_PATH,
        model_logs_path: Path = DEFAULT_MODEL_LOGS_PATH,
        selected_features_path: Path = DEFAULT_SELECTED_FEATURES_PATH,
    ) -> None:
        self.model_path = Path(model_path)
        self.model_logs_path = Path(model_logs_path)
        self.selected_features_path = Path(selected_features_path)

        self.pipeline = self._load_model()
        self.model_logs = self._load_json_if_exists(self.model_logs_path)
        self.selected_features_payload = self._load_json_if_exists(self.selected_features_path)

    def _load_model(self):
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"No se encontró el modelo en la ruta configurada: {self.model_path}"
            )
        return joblib.load(self.model_path)

    @staticmethod
    def _load_json_if_exists(path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def is_loaded(self) -> bool:
        return self.pipeline is not None

    def get_model_info(self) -> Dict[str, Any]:
        selected_training_features = self.model_logs.get("selected_training_features", [])
        top_features = self.selected_features_payload.get("selected_features", [])

        return {
            "model_name": self.model_logs.get("model_name", "logistic_regression"),
            "training_mode": self.model_logs.get("training_mode", "selected"),
            "model_path": str(self.model_path),
            "run_dir": self.model_logs.get("run_dir"),
            "selected_training_features": selected_training_features,
            "top_features": top_features,
        }

    @staticmethod
    def _resolve_risk_category(probability: float) -> str:
        if probability < 0.30:
            return "LOW"
        if probability < 0.60:
            return "MEDIUM"
        return "HIGH"

    @staticmethod
    def _resolve_decision(probability: float) -> str:
        if probability < 0.40:
            return "APPROVE"
        if probability < 0.65:
            return "REVIEW"
        return "REJECT"

    def predict(self, payload: RiskRequest) -> Dict[str, Any]:
        input_df = pd.DataFrame([payload.model_dump()])

        probability = float(self.pipeline.predict_proba(input_df)[0, 1])
        risk_category = self._resolve_risk_category(probability)
        decision = self._resolve_decision(probability)

        top_features: List[str] = self.selected_features_payload.get("selected_features", [])

        return {
            "probability_of_default": round(probability, 6),
            "risk_category": risk_category,
            "decision": decision,
            "top_features": top_features,
        }
