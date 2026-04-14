"""Tests for the ML client adapter and mock server."""

import pytest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from backend.ml_client.mock_server import app as mock_app
from backend.ml_client.client import MLClient
from backend.ml_client.schemas import (
    CreditPrediction,
    HealthResponse,
    ImprovementFactor,
    ModelInfoResponse,
    ProductType,
    RiskRequest,
    RiskResponse,
    ScoreBand,
)


# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------

@pytest.fixture
def mock_server():
    """Synchronous test client for the mock FastAPI app."""
    return TestClient(mock_app)


@pytest.fixture
def good_request() -> RiskRequest:
    """High-income banked user with good rates — should APPROVE."""
    return RiskRequest(
        declared_income=5_000_000,
        is_banked=1,
        employment_type="formal",
        age=35,
        city_type="urban",
        total_sessions=15,
        pct_conversion=0.80,
        tx_income_pct=0.60,
        payments_count=20,
        on_time_rate=0.95,
        overdue_rate=0.02,
        avg_decision_score=0.85,
    )


@pytest.fixture
def bad_request() -> RiskRequest:
    """Low-income unbanked user with bad rates — should REJECT."""
    return RiskRequest(
        declared_income=400_000,
        is_banked=0,
        employment_type="informal",
        age=20,
        city_type="rural",
        total_sessions=2,
        pct_conversion=0.10,
        tx_income_pct=0.05,
        payments_count=3,
        on_time_rate=0.20,
        overdue_rate=0.60,
        avg_decision_score=0.15,
    )


# =======================================================================
# MOCK SERVER — /risk-score
# =======================================================================

class TestMockServerRiskScore:

    def test_eligible_user(self, mock_server, good_request):
        resp = mock_server.post("/risk-score", json=good_request.model_dump(mode="json"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["decision"] == "APPROVE"
        assert data["risk_category"] == "LOW"
        assert data["probability_of_default"] < 0.40

    def test_ineligible_user(self, mock_server, bad_request):
        resp = mock_server.post("/risk-score", json=bad_request.model_dump(mode="json"))
        assert resp.status_code == 200
        data = resp.json()
        # Mock heuristic max p_default ~0.48 → REVIEW/MEDIUM (not APPROVE)
        assert data["decision"] != "APPROVE"
        assert data["risk_category"] != "LOW"
        assert data["probability_of_default"] >= 0.40

    def test_returns_valid_schema(self, mock_server, good_request):
        resp = mock_server.post("/risk-score", json=good_request.model_dump(mode="json"))
        risk = RiskResponse(**resp.json())
        assert 0.0 <= risk.probability_of_default <= 1.0
        assert risk.risk_category in ("LOW", "MEDIUM", "HIGH")
        assert risk.decision in ("APPROVE", "REVIEW", "REJECT")
        assert isinstance(risk.top_features, list)
        assert len(risk.top_features) > 0

    def test_deterministic(self, mock_server, good_request):
        body = good_request.model_dump(mode="json")
        r1 = mock_server.post("/risk-score", json=body).json()
        r2 = mock_server.post("/risk-score", json=body).json()
        assert r1["probability_of_default"] == r2["probability_of_default"]
        assert r1["decision"] == r2["decision"]

    def test_rejects_missing_field(self, mock_server):
        resp = mock_server.post("/risk-score", json={"declared_income": 1_000_000})
        assert resp.status_code == 422


# =======================================================================
# MOCK SERVER — /health
# =======================================================================

class TestMockServerHealth:

    def test_returns_ok(self, mock_server):
        resp = mock_server.get("/health")
        assert resp.status_code == 200
        h = HealthResponse(**resp.json())
        assert h.status == "ok"
        assert h.model_loaded is True


# =======================================================================
# MOCK SERVER — /model-info
# =======================================================================

class TestMockServerModelInfo:

    def test_returns_valid_schema(self, mock_server):
        resp = mock_server.get("/model-info")
        assert resp.status_code == 200
        info = ModelInfoResponse(**resp.json())
        assert info.model_name
        assert isinstance(info.top_features, list)
        assert len(info.top_features) > 0
        assert isinstance(info.selected_training_features, list)


# =======================================================================
# ML CLIENT — async tests with mocked HTTP
# =======================================================================

_FAKE_REQUEST = httpx.Request("POST", "http://test")


def _ok_response(body: dict, status: int = 200) -> httpx.Response:
    import json as _json
    return httpx.Response(
        status_code=status,
        content=_json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        request=_FAKE_REQUEST,
    )


def _err_response(status: int = 500) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        content=b'{"error": "fail"}',
        request=_FAKE_REQUEST,
    )


_MOCK_RISK_RESPONSE = {
    "probability_of_default": 0.12,
    "risk_category": "LOW",
    "decision": "APPROVE",
    "top_features": ["on_time_rate", "is_banked"],
}


class TestMLClientPredict:

    @pytest.mark.asyncio
    async def test_predict_parses_response(self, good_request):
        client = MLClient(base_url="http://fake:8001")
        with patch("backend.ml_client.client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.post.return_value = _ok_response(_MOCK_RISK_RESPONSE)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            pred = await client.predict(good_request)

        assert isinstance(pred, CreditPrediction)
        assert pred.eligible is True
        assert pred.p_default == 0.12
        assert pred.score_band == ScoreBand.low_risk
        assert pred.risk_category == "LOW"
        assert pred.decision == "APPROVE"
        assert "on_time_rate" in pred.top_features

    @pytest.mark.asyncio
    async def test_raises_on_4xx(self, good_request):
        client = MLClient(base_url="http://fake:8001")
        with patch("backend.ml_client.client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.post.return_value = _err_response(422)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            with pytest.raises(httpx.HTTPStatusError):
                await client.predict(good_request)

        assert mock_http.post.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_5xx(self, good_request):
        client = MLClient(base_url="http://fake:8001")
        with patch("backend.ml_client.client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.post.return_value = _err_response(500)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            with patch("backend.ml_client.client.asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(ConnectionError, match="failed after 3 attempts"):
                    await client.predict(good_request)

        assert mock_http.post.call_count == 3


# =======================================================================
# ML CLIENT — predict_raw
# =======================================================================

class TestMLClientPredictRaw:

    @pytest.mark.asyncio
    async def test_returns_risk_response(self, good_request):
        client = MLClient(base_url="http://fake:8001")
        with patch("backend.ml_client.client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.post.return_value = _ok_response(_MOCK_RISK_RESPONSE)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            resp = await client.predict_raw(good_request)

        assert isinstance(resp, RiskResponse)
        assert resp.probability_of_default == 0.12
        assert resp.risk_category == "LOW"
        assert resp.decision == "APPROVE"
        assert resp.top_features == ["on_time_rate", "is_banked"]


# =======================================================================
# IMPROVEMENT FACTORS
# =======================================================================

class TestImprovementFactors:

    @pytest.mark.asyncio
    async def test_bad_user_gets_factors(self, bad_request):
        prediction = CreditPrediction(
            eligible=False, p_default=0.85, score_band=ScoreBand.high_risk,
            factors=[], risk_category="HIGH", decision="REJECT", top_features=[],
        )
        client = MLClient()
        factors = await client.get_improvement_factors(bad_request, prediction)
        assert len(factors) > 0
        assert all(isinstance(f, ImprovementFactor) for f in factors)

    @pytest.mark.asyncio
    async def test_factors_sorted_by_reduction(self, bad_request):
        prediction = CreditPrediction(
            eligible=False, p_default=0.85, score_band=ScoreBand.high_risk,
            factors=[], risk_category="HIGH", decision="REJECT", top_features=[],
        )
        client = MLClient()
        factors = await client.get_improvement_factors(bad_request, prediction)
        reductions = [f.potential_reduction for f in factors]
        assert reductions == sorted(reductions, reverse=True)

    @pytest.mark.asyncio
    async def test_good_user_fewer_factors(self, good_request):
        prediction = CreditPrediction(
            eligible=True, p_default=0.10, score_band=ScoreBand.low_risk,
            max_amount=2_000_000, recommended_product=ProductType.micro,
            factors=[], risk_category="LOW", decision="APPROVE", top_features=[],
        )
        client = MLClient()
        factors = await client.get_improvement_factors(good_request, prediction)
        assert len(factors) < 3

    @pytest.mark.asyncio
    async def test_suggestions_in_spanish(self, bad_request):
        prediction = CreditPrediction(
            eligible=False, p_default=0.85, score_band=ScoreBand.high_risk,
            factors=[], risk_category="HIGH", decision="REJECT", top_features=[],
        )
        client = MLClient()
        factors = await client.get_improvement_factors(bad_request, prediction)
        for f in factors:
            assert f.suggestion
            assert any(
                word in f.suggestion.lower()
                for word in ["tu", "paga", "evita", "usa", "abre", "solicita"]
            )

    @pytest.mark.asyncio
    async def test_unbanked_gets_banking_suggestion(self, bad_request):
        assert bad_request.is_banked == 0
        prediction = CreditPrediction(
            eligible=False, p_default=0.55, score_band=ScoreBand.high_risk,
            factors=[], risk_category="HIGH", decision="REJECT", top_features=[],
        )
        client = MLClient()
        factors = await client.get_improvement_factors(bad_request, prediction)
        banking = [f for f in factors if f.factor_name == "is_banked"]
        assert len(banking) == 1
        assert "cuenta bancaria" in banking[0].suggestion.lower()
