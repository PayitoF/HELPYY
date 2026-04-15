"""ML Client adapter — consumes the MLRepo real API.

Endpoints:
    POST /risk-score  → RiskRequest → RiskResponse
    GET  /health      → HealthResponse
    GET  /model-info  → ModelInfoResponse

The client translates RiskResponse into CreditPrediction for agent consumption.
Retry with exponential backoff on transient failures.
"""

import asyncio
import logging
import os

import httpx

from backend.ml_client.contract import PRODUCT_LIMITS
from backend.ml_client.schemas import (
    CreditPrediction,
    HealthResponse,
    ImprovementFactor,
    ModelInfoResponse,
    ProductType,
    RiskFactor,
    RiskRequest,
    RiskResponse,
    ScoreBand,
)

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 2
_DEFAULT_TIMEOUT = 10


class MLClient:
    """Adapter for the MLRepo scoring API."""

    def __init__(self, base_url: str | None = None, timeout: float = _DEFAULT_TIMEOUT):
        self.base_url = (base_url or os.getenv("ML_SERVICE_URL", "http://localhost:8001")).rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def predict(self, request: RiskRequest) -> CreditPrediction:
        """POST /risk-score → CreditPrediction. Falls back to embedded model."""
        import time as _time
        t0 = _time.perf_counter()
        try:
            data = await self._post("/risk-score", request.model_dump(mode="json"))
        except ConnectionError:
            logger.warning("ML service unavailable — using embedded predictor")
            from backend.ml_client.embedded_predictor import predict_embedded
            data = predict_embedded(request.model_dump(mode="json"))
        resp = RiskResponse(**data)
        latency = (_time.perf_counter() - t0) * 1000
        logger.info("ML predict: %.0fms category=%s decision=%s", latency, resp.risk_category, resp.decision)
        return self._to_credit_prediction(resp, request)

    async def predict_raw(self, request: RiskRequest) -> RiskResponse:
        """POST /risk-score → raw RiskResponse."""
        data = await self._post("/risk-score", request.model_dump(mode="json"))
        return RiskResponse(**data)

    async def health(self) -> HealthResponse:
        """GET /health."""
        data = await self._get("/health")
        return HealthResponse(**data)

    async def get_model_info(self) -> ModelInfoResponse:
        """GET /model-info."""
        data = await self._get("/model-info")
        return ModelInfoResponse(**data)

    async def get_improvement_factors(
        self, request: RiskRequest, prediction: CreditPrediction,
    ) -> list[ImprovementFactor]:
        """Compute actionable improvements client-side."""
        factors: list[ImprovementFactor] = []
        p = prediction.p_default

        candidates = [
            ("on_time_rate", request.on_time_rate, 0.90, 0.54,
             "Paga tus cuotas a tiempo. Cada pago puntual mejora tu perfil crediticio."),
            ("overdue_rate", request.overdue_rate, 0.05, 0.20,
             "Evita atrasos mayores a 30 días. Ponte al día con pagos pendientes."),
            ("pct_conversion", request.pct_conversion, 0.60, 0.31,
             "Usa la app regularmente y completa los flujos. Tu actividad digital demuestra compromiso financiero."),
            ("is_banked", float(request.is_banked), 1.0, 0.35,
             "Abre una cuenta bancaria. Estar bancarizado mejora tu perfil de riesgo."),
        ]

        for name, current, target, weight, suggestion in candidates:
            if name == "overdue_rate":
                if current <= target:
                    continue
                delta = current - target
            else:
                if current >= target:
                    continue
                delta = target - current

            reduction = min(p * (1 - p) * weight * delta, p)
            factors.append(ImprovementFactor(
                factor_name=name,
                current_value=round(current, 3),
                target_value=round(target, 3),
                impact_weight=weight,
                potential_reduction=round(max(0.0, reduction), 4),
                suggestion=suggestion,
            ))

        factors.sort(key=lambda f: f.potential_reduction, reverse=True)
        return factors

    # ------------------------------------------------------------------
    # Translation: RiskResponse → CreditPrediction
    # ------------------------------------------------------------------

    def _to_credit_prediction(self, resp: RiskResponse, req: RiskRequest) -> CreditPrediction:
        eligible = resp.decision == "APPROVE"
        p = resp.probability_of_default

        band_map = {"LOW": ScoreBand.low_risk, "MEDIUM": ScoreBand.medium_risk, "HIGH": ScoreBand.high_risk}
        score_band = band_map.get(resp.risk_category, ScoreBand.high_risk)

        max_amount = self._compute_max_amount(p, req.declared_income) if eligible else None
        product = self._recommend_product(max_amount) if eligible else None

        factors = self._build_factors(req, resp)

        return CreditPrediction(
            eligible=eligible,
            p_default=round(p, 4),
            score_band=score_band,
            max_amount=round(max_amount, -3) if max_amount else None,
            recommended_product=product,
            factors=factors,
            risk_category=resp.risk_category,
            decision=resp.decision,
            top_features=resp.top_features,
        )

    @staticmethod
    def _compute_max_amount(p_default: float, income: float) -> float:
        if p_default < 0.20:
            multiplier = 3.0 - (p_default / 0.20) * 1.5
            cap = PRODUCT_LIMITS["micro"]["max_amount"]
        else:
            multiplier = 1.5 - ((p_default - 0.20) / 0.20) * 1.0
            cap = PRODUCT_LIMITS["nano"]["max_amount"]
        amount = income * max(multiplier, 0.5)
        return max(PRODUCT_LIMITS["nano"]["min_amount"], min(amount, cap))

    @staticmethod
    def _recommend_product(max_amount: float | None) -> ProductType | None:
        if max_amount is None:
            return None
        if max_amount >= PRODUCT_LIMITS["micro"]["min_amount"]:
            return ProductType.micro
        return ProductType.nano

    @staticmethod
    def _build_factors(req: RiskRequest, resp: RiskResponse) -> list[RiskFactor]:
        raw = [
            RiskFactor(name="on_time_rate", impact="positive" if req.on_time_rate >= 0.7 else "negative", weight=0.54),
            RiskFactor(name="is_banked", impact="positive" if req.is_banked else "negative", weight=0.35),
            RiskFactor(
                name="pct_conversion",
                impact="positive" if req.pct_conversion >= 0.5 else "negative",
                weight=0.31,
            ),
            RiskFactor(name="overdue_rate", impact="positive" if req.overdue_rate <= 0.1 else "negative", weight=0.20),
            RiskFactor(
                name="declared_income",
                impact="positive" if req.declared_income >= 1_500_000 else "negative",
                weight=0.10,
            ),
        ]
        raw.sort(key=lambda f: f.weight, reverse=True)
        return raw[:5]

    # ------------------------------------------------------------------
    # HTTP with retry
    # ------------------------------------------------------------------

    async def _get(self, path: str) -> dict | list:
        return await self._request("GET", path)

    async def _post(self, path: str, json_body: dict) -> dict:
        return await self._request("POST", path, json_body=json_body)

    async def _request(self, method: str, path: str, json_body: dict | None = None) -> dict | list:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
                    if method == "GET":
                        resp = await client.get(url)
                    else:
                        resp = await client.post(url, json=json_body)
                    resp.raise_for_status()
                    return resp.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    raise
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
