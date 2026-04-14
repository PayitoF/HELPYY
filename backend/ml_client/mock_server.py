"""Mock ML service — replicates the MLRepo Risk Generating Process.

Implements the exact same scoring logic as the MLRepo (clients_generator.py,
risk_feature_builder.py, target_builder.py) so the agent platform can develop
against realistic responses without depending on the ML team.

Run standalone:
    uvicorn backend.ml_client.mock_server:app --host 0.0.0.0 --port 8001 --reload
"""

import hashlib
import math
from datetime import date, timedelta

from fastapi import FastAPI

from backend.ml_client.contract import (
    BASE_RISK_WEIGHTS,
    DEFAULT_BASE_RATE,
    PRODUCT_LIMITS,
    RISK_INDEX_WEIGHTS,
    SCORE_BANDS,
)
from backend.ml_client.schemas import (
    CreditPrediction,
    FeatureSpec,
    ModelInfo,
    PredictRequest,
    ProductType,
    RiskFactor,
    ScoreBand,
    ScoreEntry,
)

app = FastAPI(title="ML Mock Service — HelpyHand", version="1.0.0")


# -----------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "ml-mock"}


# -----------------------------------------------------------------------
# POST /api/ml/predict — full RGP scoring
# -----------------------------------------------------------------------

@app.post("/api/ml/predict")
async def predict(request: PredictRequest) -> CreditPrediction:
    # Stage 1: base_risk_score from demographics
    base_risk = _compute_base_risk_score(request)

    # Stage 2: risk_index from demographics + behavioral
    on_time = request.on_time_rate if request.on_time_rate is not None else 0.0
    overdue = request.overdue_rate if request.overdue_rate is not None else 0.0
    rejection = request.rejection_rate if request.rejection_rate is not None else 0.0
    conversion = request.pct_conversion if request.pct_conversion is not None else 0.0
    is_banked_int = 1.0 if request.is_banked else 0.0

    risk_index_raw = (
        RISK_INDEX_WEIGHTS["on_time_rate"] * (1 - on_time)
        + RISK_INDEX_WEIGHTS["overdue_rate"] * overdue
        + RISK_INDEX_WEIGHTS["rejection_rate"] * rejection
        + RISK_INDEX_WEIGHTS["base_risk_score"] * base_risk
        + RISK_INDEX_WEIGHTS["pct_conversion"] * (1 - conversion)
        + RISK_INDEX_WEIGHTS["declared_income"] * (1 / (1 + request.declared_income))
        + RISK_INDEX_WEIGHTS["is_banked"] * (1 - is_banked_int)
    )
    # Normalize to approximately [0,1] — use the theoretical max/min
    # Max occurs when all bad: on_time=0, overdue=1, rejection=1, base_risk=1,
    # conversion=0, income=min, not_banked=1
    theoretical_max = sum(RISK_INDEX_WEIGHTS.values())
    risk_index = max(0.0, min(1.0, risk_index_raw / theoretical_max))

    # Stage 3: p_default via sigmoid
    intercept = -math.log(1 / DEFAULT_BASE_RATE - 1)
    logits = (
        intercept
        + 4.0 * risk_index
        + 2.0 * (1 - on_time)
        + 1.5 * overdue
        + 1.8 * rejection
        - 0.8 * conversion
    )
    p_default = 1 / (1 + math.exp(-logits))

    # Score band
    score_band = _score_band(p_default)

    # Eligibility + max amount
    eligible = p_default < 0.50
    max_amount = _compute_max_amount(p_default, request.declared_income) if eligible else None
    recommended_product = _recommend_product(max_amount) if eligible else None

    # Risk factors (top contributors)
    factors = _build_factors(request, base_risk, on_time, overdue, rejection, conversion)

    # Confidence: higher when more behavioral data is available
    behavioral_count = sum(
        1 for v in [
            request.on_time_rate, request.overdue_rate, request.rejection_rate,
            request.pct_conversion, request.total_sessions, request.tx_count,
            request.apps_count,
        ] if v is not None
    )
    confidence = 0.55 + 0.065 * behavioral_count  # 0.55 (demo only) → ~1.0 (all 7)

    return CreditPrediction(
        eligible=eligible,
        p_default=round(p_default, 4),
        risk_index=round(risk_index, 4),
        score_band=score_band,
        max_amount=round(max_amount, -3) if max_amount else None,  # round to thousands
        recommended_product=recommended_product,
        confidence=round(min(confidence, 1.0), 2),
        factors=factors,
    )


# -----------------------------------------------------------------------
# GET /api/ml/score-history/{client_id}
# -----------------------------------------------------------------------

@app.get("/api/ml/score-history/{client_id}")
async def score_history(client_id: str) -> list[ScoreEntry]:
    """Generate deterministic synthetic score history based on client_id hash."""
    # Use client_id hash to seed deterministic but varied history
    seed = int(hashlib.md5(client_id.encode()).hexdigest()[:8], 16)
    today = date.today()
    entries: list[ScoreEntry] = []

    # Generate 6 months of history
    base_p = 0.15 + 0.55 * ((seed % 100) / 100)  # [0.15, 0.70] range
    trend = -0.02 if seed % 3 != 0 else 0.01  # most clients improving

    for i in range(6):
        month_date = today - timedelta(days=30 * (5 - i))
        noise = 0.03 * math.sin(seed + i * 1.7)
        p = max(0.02, min(0.95, base_p + trend * i + noise))
        ri = max(0.0, min(1.0, p * 0.8 + noise * 0.5))
        band = _score_band(p)
        entries.append(ScoreEntry(
            date=month_date.isoformat(),
            p_default=round(p, 4),
            risk_index=round(ri, 4),
            score_band=band,
            eligible=p < 0.50,
        ))

    return entries


# -----------------------------------------------------------------------
# GET /api/ml/features-spec
# -----------------------------------------------------------------------

@app.get("/api/ml/features-spec")
async def features_spec() -> list[FeatureSpec]:
    """Return the exact feature specification matching the MLRepo model."""
    return [
        # Demographic (required)
        FeatureSpec(
            name="declared_income", type="float", required=True,
            description="Monthly declared income in COP",
            range_min=300_000, range_max=15_000_000,
            weight_in_risk_index=0.2,
        ),
        FeatureSpec(
            name="employment_type", type="str", required=True,
            description="Employment category",
            allowed_values=["informal", "formal", "independent"],
        ),
        FeatureSpec(
            name="is_banked", type="bool", required=True,
            description="Whether the client has an existing bank account",
            weight_in_risk_index=0.2,
        ),
        FeatureSpec(
            name="age", type="int", required=True,
            description="Client age in years",
            range_min=18, range_max=74,
        ),
        FeatureSpec(
            name="city_type", type="str", required=True,
            description="Urban or rural location",
            allowed_values=["urban", "rural"],
        ),
        FeatureSpec(
            name="education_level", type="str", required=True,
            description="Highest education level achieved",
            allowed_values=["none", "primary", "secondary", "technical", "university"],
        ),
        FeatureSpec(
            name="household_size", type="int", required=True,
            description="Number of household members",
            range_min=1, range_max=7,
        ),
        # Behavioral (optional)
        FeatureSpec(
            name="on_time_rate", type="float", required=False,
            description="Payment punctuality rate (dpd <= 0)",
            range_min=0.0, range_max=1.0,
            weight_in_risk_index=0.6, coef_in_p_default=2.0,
        ),
        FeatureSpec(
            name="overdue_rate", type="float", required=False,
            description="Severe delinquency rate (dpd > 30 days)",
            range_min=0.0, range_max=1.0,
            weight_in_risk_index=0.4, coef_in_p_default=1.5,
        ),
        FeatureSpec(
            name="rejection_rate", type="float", required=False,
            description="Loan application rejection rate",
            range_min=0.0, range_max=1.0,
            weight_in_risk_index=0.3, coef_in_p_default=1.8,
        ),
        FeatureSpec(
            name="pct_conversion", type="float", required=False,
            description="Digital session conversion rate",
            range_min=0.0, range_max=1.0,
            weight_in_risk_index=0.2, coef_in_p_default=-0.8,
        ),
        FeatureSpec(
            name="total_sessions", type="int", required=False,
            description="Total digital sessions",
            range_min=0, range_max=100,
        ),
        FeatureSpec(
            name="tx_count", type="int", required=False,
            description="Total transactions",
            range_min=0, range_max=200,
        ),
        FeatureSpec(
            name="apps_count", type="int", required=False,
            description="Total loan applications submitted",
            range_min=0, range_max=20,
        ),
    ]


# -----------------------------------------------------------------------
# GET /api/ml/model-info
# -----------------------------------------------------------------------

@app.get("/api/ml/model-info")
async def model_info() -> ModelInfo:
    return ModelInfo(
        model_type="heuristic_rgp",
        version="1.0.0",
        last_updated="2025-03-15",
        base_rate=DEFAULT_BASE_RATE,
        n_features=14,
        n_demographic_features=7,
        n_behavioral_features=7,
        metrics={
            "default_rate": DEFAULT_BASE_RATE,
            "methodology": "Risk Generating Process (hand-crafted logistic)",
            "n_synthetic_clients": 20_000,
        },
        feature_importances={
            "on_time_rate": 2.6,       # 0.6 (risk_index) + 2.0 (p_default)
            "rejection_rate": 2.1,     # 0.3 + 1.8
            "overdue_rate": 1.9,       # 0.4 + 1.5
            "pct_conversion": 1.0,     # 0.2 + 0.8
            "base_risk_score": 0.25,
            "declared_income": 0.2,
            "is_banked": 0.2,
        },
    )


# -----------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------

def _compute_base_risk_score(req: PredictRequest) -> float:
    """Stage 1: demographic risk score (from clients_generator.py)."""
    # f_income: inverse log income normalized
    log_income = math.log(req.declared_income + 1)
    log_max = math.log(15_000_001)  # max income + 1
    f_income = (log_max - log_income) / log_max

    # f_employment
    emp_scores = {"informal": 1.0, "independent": 0.65, "formal": 0.0}
    f_emp = emp_scores.get(req.employment_type.value, 0.5)

    # f_banked
    f_banked = 0.0 if req.is_banked else 0.8

    # f_age
    if req.age < 22:
        f_age = 0.7
    elif req.age > 60:
        f_age = 0.5
    else:
        f_age = 0.0

    # f_city
    f_city = 0.3 if req.city_type.value == "rural" else 0.0

    # f_education
    edu_scores = {"none": 0.6, "primary": 0.4, "secondary": 0.2, "technical": 0.0, "university": 0.0}
    f_edu = edu_scores.get(req.education_level.value, 0.0)

    w = BASE_RISK_WEIGHTS
    raw = (
        w["f_income"] * f_income
        + w["f_employment"] * f_emp
        + w["f_banked"] * f_banked
        + w["f_age"] * f_age
        + w["f_city"] * f_city
        + w["f_education"] * f_edu
    )

    # Normalize: theoretical max = sum of all weights * max factor values
    theoretical_max = (
        w["f_income"] * 1.0
        + w["f_employment"] * 1.0
        + w["f_banked"] * 0.8
        + w["f_age"] * 0.7
        + w["f_city"] * 0.3
        + w["f_education"] * 0.6
    )
    return max(0.0, min(1.0, raw / theoretical_max))


def _score_band(p_default: float) -> ScoreBand:
    for band_name, (low, high) in SCORE_BANDS.items():
        if low <= p_default < high:
            return ScoreBand(band_name)
    return ScoreBand.high_risk


def _compute_max_amount(p_default: float, income: float) -> float:
    """Eligible clients get a max amount inversely proportional to risk.

    Low risk → up to 3x monthly income (capped at 2M).
    Medium risk → up to 1.5x monthly income (capped at 500K).
    """
    if p_default < 0.20:
        multiplier = 3.0 - (p_default / 0.20) * 1.5  # 3.0 → 1.5
        cap = PRODUCT_LIMITS["micro"]["max_amount"]
    else:
        multiplier = 1.5 - ((p_default - 0.20) / 0.30) * 1.0  # 1.5 → 0.5
        cap = PRODUCT_LIMITS["nano"]["max_amount"]
    amount = income * max(multiplier, 0.5)
    return max(PRODUCT_LIMITS["nano"]["min_amount"], min(amount, cap))


def _recommend_product(max_amount: float | None) -> ProductType | None:
    if max_amount is None:
        return None
    if max_amount >= PRODUCT_LIMITS["micro"]["min_amount"]:
        return ProductType.micro
    return ProductType.nano


def _build_factors(
    req: PredictRequest,
    base_risk: float,
    on_time: float,
    overdue: float,
    rejection: float,
    conversion: float,
) -> list[RiskFactor]:
    """Build top risk factors sorted by combined impact."""
    raw_factors = [
        RiskFactor(
            name="on_time_rate",
            impact="positive" if on_time >= 0.7 else "negative",
            weight=2.6,
            current_value=round(on_time, 3),
            target_value=0.90,
        ),
        RiskFactor(
            name="rejection_rate",
            impact="positive" if rejection <= 0.2 else "negative",
            weight=2.1,
            current_value=round(rejection, 3),
            target_value=0.10,
        ),
        RiskFactor(
            name="overdue_rate",
            impact="positive" if overdue <= 0.1 else "negative",
            weight=1.9,
            current_value=round(overdue, 3),
            target_value=0.05,
        ),
        RiskFactor(
            name="pct_conversion",
            impact="positive" if conversion >= 0.5 else "negative",
            weight=1.0,
            current_value=round(conversion, 3),
            target_value=0.60,
        ),
        RiskFactor(
            name="base_risk_score",
            impact="positive" if base_risk <= 0.3 else "negative",
            weight=0.25,
            current_value=round(base_risk, 3),
        ),
        RiskFactor(
            name="declared_income",
            impact="positive" if req.declared_income >= 1_500_000 else "negative",
            weight=0.2,
            current_value=req.declared_income,
        ),
        RiskFactor(
            name="is_banked",
            impact="positive" if req.is_banked else "negative",
            weight=0.2,
            current_value=1.0 if req.is_banked else 0.0,
            target_value=1.0,
        ),
    ]
    # Sort by weight desc, return top 5
    raw_factors.sort(key=lambda f: f.weight, reverse=True)
    return raw_factors[:5]
