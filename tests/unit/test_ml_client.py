"""Tests for the ML client adapter and mock server."""

import pytest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from backend.ml_client.mock_server import app as mock_app
from backend.ml_client.client import MLClient
from backend.ml_client.schemas import (
    CreditPrediction,
    EmploymentType,
    CityType,
    EducationLevel,
    FeatureSpec,
    ImprovementFactor,
    ModelInfo,
    PredictRequest,
    ProductType,
    ScoreBand,
    ScoreEntry,
)


# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------

@pytest.fixture
def mock_server():
    """Synchronous test client for the mock FastAPI app."""
    return TestClient(mock_app)


@pytest.fixture
def good_features() -> PredictRequest:
    """High-income formal banked user — should be eligible."""
    return PredictRequest(
        declared_income=5_000_000,
        employment_type=EmploymentType.formal,
        is_banked=True,
        age=35,
        city_type=CityType.urban,
        education_level=EducationLevel.university,
        household_size=3,
        on_time_rate=0.95,
        overdue_rate=0.02,
        rejection_rate=0.05,
        pct_conversion=0.70,
    )


@pytest.fixture
def bad_features() -> PredictRequest:
    """Low-income informal unbanked user — should be ineligible."""
    return PredictRequest(
        declared_income=400_000,
        employment_type=EmploymentType.informal,
        is_banked=False,
        age=20,
        city_type=CityType.rural,
        education_level=EducationLevel.primary,
        household_size=6,
        on_time_rate=0.20,
        overdue_rate=0.60,
        rejection_rate=0.80,
        pct_conversion=0.10,
    )


@pytest.fixture
def new_user_features() -> PredictRequest:
    """New user with demographics only — no behavioral data."""
    return PredictRequest(
        declared_income=1_500_000,
        employment_type=EmploymentType.independent,
        is_banked=False,
        age=28,
        city_type=CityType.urban,
        education_level=EducationLevel.secondary,
        household_size=2,
    )


# =======================================================================
# MOCK SERVER — direct endpoint tests
# =======================================================================

class TestMockServerPredict:
    """Test the mock server /predict endpoint directly."""

    def test_predict_eligible_user(self, mock_server, good_features):
        resp = mock_server.post(
            "/api/ml/predict", json=good_features.model_dump(mode="json"),
        )
        assert resp.status_code == 200
        data = resp.json()
        pred = CreditPrediction(**data)
        assert pred.eligible is True
        assert pred.p_default < 0.50
        assert pred.score_band in (ScoreBand.low_risk, ScoreBand.medium_risk)
        assert pred.max_amount is not None
        assert pred.max_amount > 0
        assert pred.recommended_product is not None
        assert pred.confidence > 0.5

    def test_predict_ineligible_user(self, mock_server, bad_features):
        resp = mock_server.post(
            "/api/ml/predict", json=bad_features.model_dump(mode="json"),
        )
        assert resp.status_code == 200
        pred = CreditPrediction(**resp.json())
        assert pred.eligible is False
        assert pred.p_default >= 0.50
        assert pred.score_band == ScoreBand.high_risk
        assert pred.max_amount is None
        assert pred.recommended_product is None

    def test_predict_new_user_no_behavioral(self, mock_server, new_user_features):
        resp = mock_server.post(
            "/api/ml/predict", json=new_user_features.model_dump(mode="json"),
        )
        assert resp.status_code == 200
        pred = CreditPrediction(**resp.json())
        # New user without history has lower confidence
        assert pred.confidence < 0.70
        # Fields are valid regardless
        assert 0.0 <= pred.p_default <= 1.0
        assert 0.0 <= pred.risk_index <= 1.0

    def test_predict_returns_factors(self, mock_server, good_features):
        resp = mock_server.post(
            "/api/ml/predict", json=good_features.model_dump(mode="json"),
        )
        pred = CreditPrediction(**resp.json())
        assert len(pred.factors) > 0
        assert len(pred.factors) <= 5
        for f in pred.factors:
            assert f.name
            assert f.impact in ("positive", "negative")
            assert f.weight > 0

    def test_predict_score_band_consistency(self, mock_server, good_features):
        """Score band must match p_default thresholds."""
        resp = mock_server.post(
            "/api/ml/predict", json=good_features.model_dump(mode="json"),
        )
        pred = CreditPrediction(**resp.json())
        if pred.p_default < 0.20:
            assert pred.score_band == ScoreBand.low_risk
        elif pred.p_default < 0.50:
            assert pred.score_band == ScoreBand.medium_risk
        else:
            assert pred.score_band == ScoreBand.high_risk

    def test_predict_rejects_invalid_income(self, mock_server):
        """Income below range should fail validation."""
        resp = mock_server.post("/api/ml/predict", json={
            "declared_income": 100_000,  # below 300K min
            "employment_type": "informal",
            "is_banked": False,
            "age": 30,
            "city_type": "urban",
            "education_level": "secondary",
            "household_size": 3,
        })
        assert resp.status_code == 422

    def test_predict_deterministic(self, mock_server, good_features):
        """Same input should produce same output."""
        body = good_features.model_dump(mode="json")
        r1 = mock_server.post("/api/ml/predict", json=body).json()
        r2 = mock_server.post("/api/ml/predict", json=body).json()
        assert r1["p_default"] == r2["p_default"]
        assert r1["risk_index"] == r2["risk_index"]


class TestMockServerScoreHistory:

    def test_returns_list(self, mock_server):
        resp = mock_server.get("/api/ml/score-history/client-001")
        assert resp.status_code == 200
        entries = [ScoreEntry(**e) for e in resp.json()]
        assert len(entries) == 6

    def test_entries_have_valid_ranges(self, mock_server):
        resp = mock_server.get("/api/ml/score-history/client-002")
        for entry in resp.json():
            se = ScoreEntry(**entry)
            assert 0.0 <= se.p_default <= 1.0
            assert 0.0 <= se.risk_index <= 1.0
            assert se.score_band in list(ScoreBand)

    def test_deterministic_per_client(self, mock_server):
        r1 = mock_server.get("/api/ml/score-history/client-abc").json()
        r2 = mock_server.get("/api/ml/score-history/client-abc").json()
        assert r1 == r2

    def test_different_clients_different_history(self, mock_server):
        r1 = mock_server.get("/api/ml/score-history/alice").json()
        r2 = mock_server.get("/api/ml/score-history/bob").json()
        assert r1[0]["p_default"] != r2[0]["p_default"]


class TestMockServerFeaturesSpec:

    def test_returns_all_features(self, mock_server):
        resp = mock_server.get("/api/ml/features-spec")
        assert resp.status_code == 200
        specs = [FeatureSpec(**s) for s in resp.json()]
        assert len(specs) == 14
        names = {s.name for s in specs}
        assert "declared_income" in names
        assert "on_time_rate" in names

    def test_required_features(self, mock_server):
        resp = mock_server.get("/api/ml/features-spec")
        specs = [FeatureSpec(**s) for s in resp.json()]
        required = [s for s in specs if s.required]
        optional = [s for s in specs if not s.required]
        assert len(required) == 7
        assert len(optional) == 7

    def test_behavioral_features_have_weights(self, mock_server):
        resp = mock_server.get("/api/ml/features-spec")
        specs = [FeatureSpec(**s) for s in resp.json()]
        on_time = next(s for s in specs if s.name == "on_time_rate")
        assert on_time.weight_in_risk_index == 0.6
        assert on_time.coef_in_p_default == 2.0


class TestMockServerModelInfo:

    def test_returns_valid_info(self, mock_server):
        resp = mock_server.get("/api/ml/model-info")
        assert resp.status_code == 200
        info = ModelInfo(**resp.json())
        assert info.model_type == "heuristic_rgp"
        assert info.version
        assert info.base_rate == 0.15
        assert info.n_features == 14
        assert "on_time_rate" in info.feature_importances

    def test_health(self, mock_server):
        resp = mock_server.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# =======================================================================
# ML CLIENT — async tests with mocked HTTP
# =======================================================================

_FAKE_REQUEST = httpx.Request("POST", "http://test")


def _ok_response(body: dict | list, status: int = 200) -> httpx.Response:
    import json
    return httpx.Response(
        status_code=status,
        content=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        request=_FAKE_REQUEST,
    )


def _err_response(status: int = 500) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        content=b'{"error": "fail"}',
        request=_FAKE_REQUEST,
    )


class TestMLClientPredict:

    @pytest.mark.asyncio
    async def test_predict_parses_response(self, good_features):
        """Client should parse a valid predict response into CreditPrediction."""
        mock_response = {
            "eligible": True, "p_default": 0.12, "risk_index": 0.25,
            "score_band": "low_risk", "max_amount": 1_500_000,
            "recommended_product": "micro", "confidence": 0.85,
            "factors": [{"name": "on_time_rate", "impact": "positive", "weight": 2.6}],
        }
        client = MLClient(base_url="http://fake:8001")
        with patch("backend.ml_client.client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.post.return_value = _ok_response(mock_response)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            pred = await client.predict(good_features)

        assert isinstance(pred, CreditPrediction)
        assert pred.eligible is True
        assert pred.p_default == 0.12
        assert pred.score_band == ScoreBand.low_risk

    @pytest.mark.asyncio
    async def test_predict_raises_on_4xx(self, good_features):
        """Client should NOT retry on 4xx errors."""
        client = MLClient(base_url="http://fake:8001")
        with patch("backend.ml_client.client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_resp = _err_response(422)
            mock_http.post.return_value = mock_resp
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            with pytest.raises(httpx.HTTPStatusError):
                await client.predict(good_features)

        # Should only have been called once (no retry on 4xx)
        assert mock_http.post.call_count == 1

    @pytest.mark.asyncio
    async def test_predict_retries_on_5xx(self, good_features):
        """Client should retry on 5xx and eventually raise ConnectionError."""
        client = MLClient(base_url="http://fake:8001")
        with patch("backend.ml_client.client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.post.return_value = _err_response(500)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            with patch("backend.ml_client.client.asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(ConnectionError, match="failed after 3 attempts"):
                    await client.predict(good_features)

        # 3 attempts total
        assert mock_http.post.call_count == 3


class TestMLClientScoreHistory:

    @pytest.mark.asyncio
    async def test_returns_list_of_entries(self):
        mock_data = [
            {"date": "2025-01-01", "p_default": 0.30, "risk_index": 0.25,
             "score_band": "medium_risk", "eligible": True},
            {"date": "2025-02-01", "p_default": 0.28, "risk_index": 0.23,
             "score_band": "medium_risk", "eligible": True},
        ]
        client = MLClient(base_url="http://fake:8001")
        with patch("backend.ml_client.client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.get.return_value = _ok_response(mock_data)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            entries = await client.get_score_history("client-001")

        assert len(entries) == 2
        assert all(isinstance(e, ScoreEntry) for e in entries)
        assert entries[0].p_default == 0.30


class TestMLClientFeatureSpec:

    @pytest.mark.asyncio
    async def test_returns_list_of_specs(self):
        mock_data = [
            {"name": "declared_income", "type": "float", "required": True,
             "description": "Monthly income", "range_min": 300_000, "range_max": 15_000_000},
        ]
        client = MLClient(base_url="http://fake:8001")
        with patch("backend.ml_client.client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.get.return_value = _ok_response(mock_data)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            specs = await client.get_feature_spec()

        assert len(specs) == 1
        assert isinstance(specs[0], FeatureSpec)
        assert specs[0].name == "declared_income"


class TestMLClientModelInfo:

    @pytest.mark.asyncio
    async def test_returns_model_info(self):
        mock_data = {
            "model_type": "heuristic_rgp", "version": "1.0.0",
            "last_updated": "2025-03-15", "base_rate": 0.15,
            "n_features": 14, "n_demographic_features": 7,
            "n_behavioral_features": 7, "metrics": {},
            "feature_importances": {"on_time_rate": 2.6},
        }
        client = MLClient(base_url="http://fake:8001")
        with patch("backend.ml_client.client.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.get.return_value = _ok_response(mock_data)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            info = await client.get_model_info()

        assert isinstance(info, ModelInfo)
        assert info.model_type == "heuristic_rgp"
        assert info.base_rate == 0.15


# =======================================================================
# IMPROVEMENT FACTORS — client-side computation
# =======================================================================

class TestImprovementFactors:

    @pytest.mark.asyncio
    async def test_returns_actionable_factors(self, bad_features):
        """Bad user should get multiple improvement suggestions."""
        prediction = CreditPrediction(
            eligible=False, p_default=0.85, risk_index=0.80,
            score_band=ScoreBand.high_risk, confidence=0.90, factors=[],
        )
        client = MLClient()
        factors = await client.get_improvement_factors(bad_features, prediction)
        assert len(factors) > 0
        assert all(isinstance(f, ImprovementFactor) for f in factors)

    @pytest.mark.asyncio
    async def test_factors_sorted_by_reduction(self, bad_features):
        prediction = CreditPrediction(
            eligible=False, p_default=0.85, risk_index=0.80,
            score_band=ScoreBand.high_risk, confidence=0.90, factors=[],
        )
        client = MLClient()
        factors = await client.get_improvement_factors(bad_features, prediction)
        reductions = [f.potential_reduction for f in factors]
        assert reductions == sorted(reductions, reverse=True)

    @pytest.mark.asyncio
    async def test_good_user_fewer_improvements(self, good_features):
        """Good user with high scores should have fewer/no improvements."""
        prediction = CreditPrediction(
            eligible=True, p_default=0.10, risk_index=0.15,
            score_band=ScoreBand.low_risk, max_amount=2_000_000,
            recommended_product=ProductType.micro, confidence=0.95, factors=[],
        )
        client = MLClient()
        factors = await client.get_improvement_factors(good_features, prediction)
        # Good user already meets most targets
        assert len(factors) < 3

    @pytest.mark.asyncio
    async def test_suggestions_are_in_spanish(self, bad_features):
        prediction = CreditPrediction(
            eligible=False, p_default=0.85, risk_index=0.80,
            score_band=ScoreBand.high_risk, confidence=0.90, factors=[],
        )
        client = MLClient()
        factors = await client.get_improvement_factors(bad_features, prediction)
        for f in factors:
            assert f.suggestion  # non-empty
            # Spanish indicators
            assert any(
                word in f.suggestion.lower()
                for word in ["tu", "paga", "evita", "usa", "abre", "solicita"]
            )

    @pytest.mark.asyncio
    async def test_unbanked_gets_banking_suggestion(self, new_user_features):
        prediction = CreditPrediction(
            eligible=False, p_default=0.55, risk_index=0.50,
            score_band=ScoreBand.high_risk, confidence=0.55, factors=[],
        )
        client = MLClient()
        factors = await client.get_improvement_factors(new_user_features, prediction)
        banking = [f for f in factors if f.factor_name == "is_banked"]
        assert len(banking) == 1
        assert "cuenta bancaria" in banking[0].suggestion.lower()
