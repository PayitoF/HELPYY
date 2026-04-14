
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_path: str


class ModelInfoResponse(BaseModel):
    model_name: str
    training_mode: str
    model_path: str
    run_dir: Optional[str] = None
    selected_training_features: List[str]
    top_features: List[str]


class RiskRequest(BaseModel):
    declared_income: float = Field(..., ge=0)
    is_banked: int = Field(..., ge=0, le=1)
    employment_type: Literal["formal", "independent", "informal"]
    age: int = Field(..., ge=18, le=100)
    city_type: Literal["urban", "rural"]
    total_sessions: int = Field(..., ge=0)
    pct_conversion: float = Field(..., ge=0.0, le=1.0)
    tx_income_pct: float = Field(..., ge=0.0)
    payments_count: int = Field(..., ge=0)
    on_time_rate: float = Field(..., ge=0.0, le=1.0)
    overdue_rate: float = Field(..., ge=0.0, le=1.0)
    avg_decision_score: float = Field(..., ge=0.0, le=1.0)


class RiskResponse(BaseModel):
    probability_of_default: float
    risk_category: Literal["LOW", "MEDIUM", "HIGH"]
    decision: Literal["APPROVE", "REVIEW", "REJECT"]
    top_features: List[str]
