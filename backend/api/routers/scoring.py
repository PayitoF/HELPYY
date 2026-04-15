"""Scoring router — loan evaluation + acceptance endpoints."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from backend.ml_client.client import MLClient
from backend.ml_client.schemas import RiskRequest
from backend.agents.credit_evaluator_agent import build_options_table, MONTHLY_RATE_DEFAULT
from backend.agents.financial_advisor_agent import build_plan

router = APIRouter()


# -----------------------------------------------------------------------
# Schemas
# -----------------------------------------------------------------------

class LoanApplicationRequest(BaseModel):
    session_id: str
    declared_income: float
    employment_type: str  # informal, formal, independent
    age: int
    city_type: str  # urban, rural
    occupation: str = "default"
    dependents: int = 0
    has_other_credits: bool = False
    requested_amount: float = 0
    purpose: str = ""


class LoanEvaluationResponse(BaseModel):
    eligible: bool
    p_default: float | None = None
    max_amount: float | None = None
    score_band: str
    options: list[dict] = []
    missions: list[dict] = []
    factors: list[dict] = []
    improvement_factors: list[dict] = []
    rejection_reasons: list[str] = []
    contract_template: dict | None = None


class AcceptLoanRequest(BaseModel):
    session_id: str
    amount: float
    term_months: int
    monthly_payment: float


class LoanAcceptanceResponse(BaseModel):
    success: bool
    loan_id: str
    message: str
    disbursement_date: str


# -----------------------------------------------------------------------
# Factor → human-readable reason mapping
# -----------------------------------------------------------------------

_FACTOR_REASONS = {
    "on_time_rate": "Tu historial de pagos puntuales necesita mejorar",
    "is_banked": "Necesitas más actividad con productos bancarios",
    "pct_conversion": "Tu actividad digital con el banco es baja",
    "overdue_rate": "Tienes pagos atrasados en tu historial",
    "declared_income": "Tus ingresos declarados son bajos para el monto solicitado",
}


# -----------------------------------------------------------------------
# POST /scoring/evaluate
# -----------------------------------------------------------------------

@router.post("/evaluate", response_model=LoanEvaluationResponse)
async def evaluate_loan(req: LoanApplicationRequest):
    """Evaluate a loan application: ML scoring + dynamic missions if rejected."""
    risk_req = RiskRequest(
        declared_income=req.declared_income,
        employment_type=req.employment_type,
        age=req.age,
        city_type=req.city_type,
        is_banked=1,
        on_time_rate=0.5,
        overdue_rate=0.0,
        pct_conversion=0.0,
        total_sessions=0,
        payments_count=0,
        tx_income_pct=0.0,
        avg_decision_score=0.5,
    )

    client = MLClient()
    prediction = await client.predict(risk_req)

    factors = [
        {"name": f.name, "impact": f.impact, "weight": f.weight}
        for f in prediction.factors
    ]

    if prediction.eligible:
        max_amount = prediction.max_amount or 500_000
        options = build_options_table(max_amount)
        return LoanEvaluationResponse(
            eligible=True,
            p_default=prediction.p_default,
            max_amount=max_amount,
            score_band=prediction.score_band.value,
            options=options,
            factors=factors,
            contract_template={
                "max_amount": max_amount,
                "options": options,
                "monthly_rate": MONTHLY_RATE_DEFAULT,
                "conditions": [
                    "Tasa efectiva anual: ~34.5%",
                    "Sin codeudor requerido para montos hasta $500.000",
                    "Desembolso en 24 horas hábiles",
                    "Pago mensual por débito automático o en sucursal",
                    "Seguro de vida incluido sin costo adicional",
                ],
            },
        )

    # Not eligible — get real improvement factors from ML
    real_improvements = await client.get_improvement_factors(risk_req, prediction)

    improvement_factors = [
        {
            "factor_name": f.factor_name,
            "current_value": f.current_value,
            "target_value": f.target_value,
            "impact_weight": f.impact_weight,
            "potential_reduction": f.potential_reduction,
            "suggestion": f.suggestion,
        }
        for f in real_improvements
    ]

    # Build missions from real ML factors (linked to model thresholds)
    # Occupation maps to personalized tips in the mission catalog
    occupation_map = {
        "vendedor ambulante": "vendedor_ambulante",
        "trabajador doméstico": "trabajador_domestico",
        "conductor": "independiente",
        "comerciante": "independiente",
        "peluquero/a": "independiente",
        "cocinero/a": "vendedor_ambulante",
    }
    occ = occupation_map.get(req.occupation.lower(), "default")
    missions = build_plan(improvement_factors, occupation=occ)

    # Enrich missions with ML context
    for mission in missions:
        matching = next(
            (f for f in improvement_factors if f["factor_name"] == mission.get("factor")),
            None,
        )
        if matching:
            mission["ml_current"] = matching["current_value"]
            mission["ml_target"] = matching["target_value"]
            mission["ml_suggestion"] = matching["suggestion"]

    negative = [f for f in factors if f["impact"] == "negative"]
    rejection_reasons = [
        _FACTOR_REASONS.get(f["name"], f"Factor: {f['name']}")
        for f in negative
    ]

    return LoanEvaluationResponse(
        eligible=False,
        p_default=prediction.p_default,
        score_band=prediction.score_band.value,
        factors=factors,
        improvement_factors=improvement_factors,
        missions=missions,
        rejection_reasons=rejection_reasons,
    )


# -----------------------------------------------------------------------
# POST /scoring/accept-loan
# -----------------------------------------------------------------------

@router.post("/accept-loan", response_model=LoanAcceptanceResponse)
async def accept_loan(req: AcceptLoanRequest):
    """Accept a loan offer (PoC — generates loan ID and returns success)."""
    return LoanAcceptanceResponse(
        success=True,
        loan_id=str(uuid.uuid4()),
        message=f"Préstamo de ${req.amount:,.0f} a {req.term_months} meses aprobado.",
        disbursement_date="En las próximas 24 horas",
    )
