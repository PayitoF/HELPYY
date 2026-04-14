
from __future__ import annotations

from fastapi import FastAPI

from src.api.predictor import PredictionService
from src.api.schemas import HealthResponse, ModelInfoResponse, RiskRequest, RiskResponse


app = FastAPI(
    title="HelpyHand Risk Scoring API",
    description="API de scoring crediticio alternativo para HelpyHand",
    version="0.1.0",
)

prediction_service = PredictionService()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        model_loaded=prediction_service.is_loaded(),
        model_path=str(prediction_service.model_path),
    )

@app.get("/")
def root():
    return {
        "message": "HelpyHand Risk Scoring API is running",
        "docs": "/docs",
        "health": "/health",
        "model_info": "/model-info"
    }

@app.get("/model-info", response_model=ModelInfoResponse)
def model_info() -> ModelInfoResponse:
    info = prediction_service.get_model_info()
    return ModelInfoResponse(**info)


@app.post("/risk-score", response_model=RiskResponse)
def risk_score(payload: RiskRequest) -> RiskResponse:
    result = prediction_service.predict(payload)
    return RiskResponse(**result)
