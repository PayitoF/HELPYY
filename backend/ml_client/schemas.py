"""Pydantic models for ML service API contract.

Two layers:
  1. RiskRequest / RiskResponse — mirror MLRepo/src/api/schemas.py EXACTLY
  2. CreditPrediction, ImprovementFactor, etc. — internal wrappers used by agents

The MLClient translates between the two layers so agents never deal with
the raw ML API format directly.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ======================================================================
# Layer 1 — MLRepo contract (MUST match MLRepo/src/api/schemas.py)
# ======================================================================

class RiskRequest(BaseModel):
    """Exact mirror of MLRepo RiskRequest."""
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
    """Exact mirror of MLRepo RiskResponse."""
    probability_of_default: float
    risk_category: Literal["LOW", "MEDIUM", "HIGH"]
    decision: Literal["APPROVE", "REVIEW", "REJECT"]
    top_features: list[str]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_path: str


class ModelInfoResponse(BaseModel):
    model_name: str
    training_mode: str
    model_path: str
    run_dir: str | None = None
    selected_training_features: list[str]
    top_features: list[str]


# ======================================================================
# Layer 2 — Internal models used by agents
# ======================================================================

class ScoreBand(str, Enum):
    low_risk = "low_risk"
    medium_risk = "medium_risk"
    high_risk = "high_risk"


class ProductType(str, Enum):
    nano = "nano"
    micro = "micro"


class RiskFactor(BaseModel):
    name: str
    impact: str = Field(..., pattern="^(positive|negative)$")
    weight: float


class CreditPrediction(BaseModel):
    """Internal prediction model consumed by agents.

    Built by MLClient from RiskResponse + business logic.
    """
    eligible: bool
    p_default: float = Field(..., ge=0.0, le=1.0)
    score_band: ScoreBand
    max_amount: float | None = None
    recommended_product: ProductType | None = None
    factors: list[RiskFactor] = Field(default_factory=list)
    risk_category: str = ""
    decision: str = ""
    top_features: list[str] = Field(default_factory=list)


class ImprovementFactor(BaseModel):
    factor_name: str
    current_value: float
    target_value: float
    impact_weight: float
    potential_reduction: float
    suggestion: str
