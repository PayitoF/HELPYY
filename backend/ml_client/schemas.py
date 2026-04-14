"""Pydantic models for ML service API contract.

These schemas define the contract between the agent platform and the ML service.
Inferred from analysis of MLRepo: clients_generator.py, risk_feature_builder.py,
target_builder.py, and loan_applications_generator.py.
"""

from pydantic import BaseModel, Field
from enum import Enum


# --------------------------------------------------------------------------
# Enums matching MLRepo categorical distributions
# --------------------------------------------------------------------------

class EmploymentType(str, Enum):
    informal = "informal"
    formal = "formal"
    independent = "independent"


class CityType(str, Enum):
    urban = "urban"
    rural = "rural"


class EducationLevel(str, Enum):
    none = "none"
    primary = "primary"
    secondary = "secondary"
    technical = "technical"
    university = "university"


class ScoreBand(str, Enum):
    low_risk = "low_risk"
    medium_risk = "medium_risk"
    high_risk = "high_risk"


class ProductType(str, Enum):
    nano = "nano"
    micro = "micro"
    reload = "reload"


# --------------------------------------------------------------------------
# Request / Response models
# --------------------------------------------------------------------------

class PredictRequest(BaseModel):
    """Features required for credit scoring.

    Demographic features are required. Behavioral features are optional
    because new users without history won't have them — the model uses
    defaults (zero values) for missing behavioral data.
    """

    # Demographic (required) — used in base_risk_score calculation
    declared_income: float = Field(
        ..., ge=300_000, le=15_000_000,
        description="Monthly declared income in COP",
    )
    employment_type: EmploymentType
    is_banked: bool
    age: int = Field(..., ge=18, le=74)
    city_type: CityType
    education_level: EducationLevel
    household_size: int = Field(..., ge=1, le=7)

    # Behavioral (optional) — used in risk_index and p_default
    on_time_rate: float | None = Field(
        None, ge=0.0, le=1.0,
        description="Payment punctuality rate (dpd <= 0)",
    )
    overdue_rate: float | None = Field(
        None, ge=0.0, le=1.0,
        description="Severe delinquency rate (dpd > 30 days)",
    )
    rejection_rate: float | None = Field(
        None, ge=0.0, le=1.0,
        description="Loan application rejection rate",
    )
    pct_conversion: float | None = Field(
        None, ge=0.0, le=1.0,
        description="Digital session conversion rate",
    )
    total_sessions: int | None = Field(None, ge=0, description="Total digital sessions")
    tx_count: int | None = Field(None, ge=0, description="Total transactions")
    apps_count: int | None = Field(None, ge=0, description="Total loan applications")


class RiskFactor(BaseModel):
    """A factor contributing to the credit decision."""

    name: str = Field(..., description="Feature name")
    impact: str = Field(..., pattern="^(positive|negative)$", description="Direction of impact")
    weight: float = Field(..., description="Relative importance weight")
    current_value: float | None = Field(None, description="Client's current value for this feature")
    target_value: float | None = Field(None, description="Recommended target to improve score")


class CreditPrediction(BaseModel):
    """ML model prediction result."""

    eligible: bool = Field(..., description="Whether the client is eligible for credit")
    p_default: float = Field(..., ge=0.0, le=1.0, description="Probability of default")
    risk_index: float = Field(..., ge=0.0, le=1.0, description="Composite risk index")
    score_band: ScoreBand
    max_amount: float | None = Field(
        None, ge=0,
        description="Maximum loan amount in COP if eligible",
    )
    recommended_product: ProductType | None = Field(
        None, description="Recommended product type based on risk",
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model confidence")
    factors: list[RiskFactor] = Field(
        default_factory=list,
        description="Top contributing risk factors",
    )


class ScoreEntry(BaseModel):
    """Historical score entry."""

    date: str = Field(..., description="ISO date string")
    p_default: float = Field(..., ge=0.0, le=1.0)
    risk_index: float = Field(..., ge=0.0, le=1.0)
    score_band: ScoreBand
    eligible: bool


class FeatureSpec(BaseModel):
    """Specification of a feature accepted by the ML model."""

    name: str
    type: str = Field(..., description="Python type: float, int, str, bool")
    required: bool
    description: str
    range_min: float | None = None
    range_max: float | None = None
    allowed_values: list[str] | None = None
    weight_in_risk_index: float | None = Field(
        None, description="Weight in risk_index formula (if applicable)",
    )
    coef_in_p_default: float | None = Field(
        None, description="Coefficient in p_default logit (if applicable)",
    )


class ModelInfo(BaseModel):
    """Metadata about the ML model."""

    model_type: str = Field(..., description="e.g., 'heuristic_rgp', 'xgboost', 'lightgbm'")
    version: str
    last_updated: str = Field(..., description="ISO date of last update")
    base_rate: float = Field(..., description="Base default rate used for intercept")
    n_features: int
    n_demographic_features: int
    n_behavioral_features: int
    metrics: dict = Field(
        default_factory=dict,
        description="Performance metrics: {default_rate, ks_statistic, gini, etc.}",
    )
    feature_importances: dict[str, float] = Field(
        default_factory=dict,
        description="Feature name → combined importance weight",
    )


class ImprovementFactor(BaseModel):
    """An actionable factor the user can improve."""

    factor_name: str
    current_value: float
    target_value: float
    impact_weight: float = Field(..., description="Combined weight from risk_index + p_default")
    potential_reduction: float = Field(
        ..., description="Estimated p_default reduction if target is reached",
    )
    suggestion: str = Field(..., description="Human-readable improvement suggestion in Spanish")


class ErrorResponse(BaseModel):
    """Standard error response from the ML service."""

    error_code: str
    message: str
    details: dict | None = None
