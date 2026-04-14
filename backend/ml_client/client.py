"""ML Client adapter — consumes the ML service API.

Same interface works against both the mock server (local) and the real ML service (prod).
Switch via ML_SERVICE_URL env var (default: http://localhost:8001).

Retry with exponential backoff on transient failures (5xx, network errors).
"""

import asyncio
import logging
import math
import os

import httpx

from backend.ml_client.contract import (
    DEFAULT_BASE_RATE,
    ENDPOINTS,
    RISK_INDEX_WEIGHTS,
)
from backend.ml_client.schemas import (
    CreditPrediction,
    FeatureSpec,
    ImprovementFactor,
    ModelInfo,
    PredictRequest,
    ScoreEntry,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds
_DEFAULT_TIMEOUT = 10  # seconds


class MLClient:
    """Adapter for the ML scoring service.

    Usage:
        client = MLClient()  # reads ML_SERVICE_URL from env
        prediction = await client.predict(PredictRequest(...))
        factors = await client.get_improvement_factors(request, prediction)
    """

    def __init__(self, base_url: str | None = None, timeout: float = _DEFAULT_TIMEOUT):
        self.base_url = (base_url or os.getenv("ML_SERVICE_URL", "http://localhost:8001")).rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def predict(self, features: PredictRequest) -> CreditPrediction:
        """POST /api/ml/predict — get credit eligibility prediction."""
        ep = ENDPOINTS["predict"]
        data = await self._post(ep["path"], features.model_dump(mode="json"))
        return CreditPrediction(**data)

    async def get_score_history(self, client_id: str) -> list[ScoreEntry]:
        """GET /api/ml/score-history/{client_id} — historical scores."""
        ep = ENDPOINTS["score_history"]
        path = ep["path"].replace("{client_id}", client_id)
        data = await self._get(path)
        return [ScoreEntry(**entry) for entry in data]

    async def get_feature_spec(self) -> list[FeatureSpec]:
        """GET /api/ml/features-spec — what features the model accepts."""
        ep = ENDPOINTS["features_spec"]
        data = await self._get(ep["path"])
        return [FeatureSpec(**spec) for spec in data]

    async def get_model_info(self) -> ModelInfo:
        """GET /api/ml/model-info — model metadata and metrics."""
        ep = ENDPOINTS["model_info"]
        data = await self._get(ep["path"])
        return ModelInfo(**data)

    async def get_improvement_factors(
        self, features: PredictRequest, prediction: CreditPrediction,
    ) -> list[ImprovementFactor]:
        """Compute actionable improvements, ordered by impact.

        Uses the RGP weights from contract.py to estimate which changes
        would most reduce p_default. Works client-side — no server call needed.
        """
        factors: list[ImprovementFactor] = []

        # Current behavioral values (default to 0 if missing)
        on_time = features.on_time_rate if features.on_time_rate is not None else 0.0
        overdue = features.overdue_rate if features.overdue_rate is not None else 0.0
        rejection = features.rejection_rate if features.rejection_rate is not None else 0.0
        conversion = features.pct_conversion if features.pct_conversion is not None else 0.0

        # Each factor: (name, current, target, combined_weight, suggestion)
        candidates = [
            (
                "on_time_rate", on_time, 0.90, 2.6,
                "Paga tus cuotas a tiempo. Cada pago puntual mejora tu perfil crediticio.",
            ),
            (
                "overdue_rate", overdue, 0.05, 1.9,
                "Evita atrasos mayores a 30 días. Ponte al día con pagos pendientes.",
            ),
            (
                "rejection_rate", rejection, 0.10, 2.1,
                "Solicita crédito solo cuando cumplas los requisitos. "
                "Muchas solicitudes rechazadas afectan tu perfil.",
            ),
            (
                "pct_conversion", conversion, 0.60, 1.0,
                "Usa la app regularmente y completa los flujos. "
                "Tu actividad digital demuestra compromiso financiero.",
            ),
            (
                "is_banked", 1.0 if features.is_banked else 0.0, 1.0, 0.2,
                "Abre una cuenta bancaria. Estar bancarizado mejora tu perfil de riesgo.",
            ),
        ]

        for name, current, target, weight, suggestion in candidates:
            # Skip factors already at or past target
            if name == "overdue_rate" or name == "rejection_rate":
                # Lower is better
                if current <= target:
                    continue
            elif name == "is_banked":
                if current >= target:
                    continue
            else:
                # Higher is better
                if current >= target:
                    continue

            # Estimate p_default reduction from improving this factor
            reduction = _estimate_p_default_reduction(
                name, current, target, prediction.risk_index, prediction.p_default,
            )

            factors.append(ImprovementFactor(
                factor_name=name,
                current_value=round(current, 3),
                target_value=round(target, 3),
                impact_weight=weight,
                potential_reduction=round(reduction, 4),
                suggestion=suggestion,
            ))

        # Sort by potential_reduction descending (biggest improvement first)
        factors.sort(key=lambda f: f.potential_reduction, reverse=True)
        return factors

    # ------------------------------------------------------------------
    # Internal HTTP methods with retry
    # ------------------------------------------------------------------

    async def _get(self, path: str) -> dict | list:
        return await self._request("GET", path)

    async def _post(self, path: str, json_body: dict) -> dict:
        return await self._request("POST", path, json_body=json_body)

    async def _request(
        self, method: str, path: str, json_body: dict | None = None,
    ) -> dict | list:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self.timeout),
                ) as client:
                    if method == "GET":
                        resp = await client.get(url)
                    else:
                        resp = await client.post(url, json=json_body)
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    raise  # Don't retry 4xx
                last_exc = exc
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc

            wait = _BACKOFF_BASE ** attempt
            logger.warning(
                "ML service request failed (attempt %d/%d): %s — retrying in %ds",
                attempt + 1, _MAX_RETRIES, last_exc, wait,
            )
            await asyncio.sleep(wait)

        raise ConnectionError(
            f"ML service request failed after {_MAX_RETRIES} attempts: {path}"
        ) from last_exc


# -----------------------------------------------------------------------
# Helper: estimate p_default reduction
# -----------------------------------------------------------------------

def _estimate_p_default_reduction(
    factor_name: str,
    current: float,
    target: float,
    current_risk_index: float,
    current_p_default: float,
) -> float:
    """Estimate how much p_default would drop if factor goes from current → target.

    Uses a linear approximation based on the RGP coefficients.
    """
    # risk_index weight contribution
    ri_weight = RISK_INDEX_WEIGHTS.get(factor_name.replace("_rate", "_rate"), 0.0)
    if factor_name == "on_time_rate":
        ri_weight = RISK_INDEX_WEIGHTS["on_time_rate"]
    elif factor_name == "overdue_rate":
        ri_weight = RISK_INDEX_WEIGHTS["overdue_rate"]
    elif factor_name == "rejection_rate":
        ri_weight = RISK_INDEX_WEIGHTS["rejection_rate"]
    elif factor_name == "pct_conversion":
        ri_weight = RISK_INDEX_WEIGHTS["pct_conversion"]
    elif factor_name == "is_banked":
        ri_weight = RISK_INDEX_WEIGHTS["is_banked"]
    else:
        ri_weight = 0.0

    delta = abs(target - current)

    # p_default logit coefficient mapping
    logit_coefs = {
        "on_time_rate": 2.0,       # on (1 - on_time_rate)
        "overdue_rate": 1.5,
        "rejection_rate": 1.8,
        "pct_conversion": 0.8,     # abs value
        "is_banked": 0.0,          # only affects via risk_index
    }
    logit_coef = logit_coefs.get(factor_name, 0.0)

    # Total logit shift from improving this factor
    # risk_index contribution: ri_weight * delta * 4.0 (the risk_index coef in logit)
    total_max = sum(RISK_INDEX_WEIGHTS.values())
    ri_logit_shift = (ri_weight * delta / total_max) * 4.0
    direct_logit_shift = logit_coef * delta

    total_shift = ri_logit_shift + direct_logit_shift

    # Convert logit shift to p_default reduction using derivative of sigmoid
    # dp/dlogit = p * (1 - p) at current p
    p = current_p_default
    dp = p * (1 - p) * total_shift

    return max(0.0, min(dp, p))  # can't reduce below 0
