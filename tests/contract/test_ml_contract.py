"""Contract tests — validate that the ML service meets the API contract.

Run against:
    - Mock server (local dev):  ML_SERVICE_URL=http://localhost:8001 pytest tests/contract/ -v -m contract
    - Real ML service (prod):   ML_SERVICE_URL=https://ml-scoring.internal pytest tests/contract/ -v -m contract

The ML team should run these against their service to verify compatibility.
All tests use the mock server's TestClient by default; set ML_SERVICE_URL
to override and test against a real HTTP endpoint.
"""

import os

import pytest
from fastapi.testclient import TestClient

from backend.ml_client.mock_server import app as mock_app
from backend.ml_client.schemas import (
    CreditPrediction,
    FeatureSpec,
    ModelInfo,
    PredictRequest,
    ScoreBand,
    ScoreEntry,
)
from backend.ml_client.contract import (
    FEATURE_RANGES,
    SCORE_BANDS,
)


# -----------------------------------------------------------------------
# Helpers — route requests to either TestClient or real HTTP
# -----------------------------------------------------------------------

def _get_client():
    """Return a TestClient for the mock, or an httpx client for real service."""
    url = os.getenv("ML_SERVICE_URL")
    if url:
        import httpx
        return httpx.Client(base_url=url, timeout=10)
    return TestClient(mock_app)


@pytest.fixture
def api():
    client = _get_client()
    yield client
    if hasattr(client, "close"):
        client.close()


def _good_request() -> dict:
    return {
        "declared_income": 3_000_000,
        "employment_type": "formal",
        "is_banked": True,
        "age": 35,
        "city_type": "urban",
        "education_level": "technical",
        "household_size": 3,
        "on_time_rate": 0.90,
        "overdue_rate": 0.05,
        "rejection_rate": 0.10,
        "pct_conversion": 0.60,
    }


def _bad_request() -> dict:
    return {
        "declared_income": 400_000,
        "employment_type": "informal",
        "is_banked": False,
        "age": 19,
        "city_type": "rural",
        "education_level": "primary",
        "household_size": 6,
        "on_time_rate": 0.15,
        "overdue_rate": 0.70,
        "rejection_rate": 0.85,
        "pct_conversion": 0.05,
    }


def _minimal_request() -> dict:
    """Only required demographic fields — no behavioral data."""
    return {
        "declared_income": 1_200_000,
        "employment_type": "independent",
        "is_banked": False,
        "age": 28,
        "city_type": "urban",
        "education_level": "secondary",
        "household_size": 2,
    }


# =======================================================================
# CONTRACT TESTS
# =======================================================================

@pytest.mark.contract
class TestPredictContract:
    """POST /api/ml/predict must conform to CreditPrediction schema."""

    def test_returns_valid_schema(self, api):
        resp = api.post("/api/ml/predict", json=_good_request())
        assert resp.status_code == 200
        pred = CreditPrediction(**resp.json())
        assert 0.0 <= pred.p_default <= 1.0
        assert 0.0 <= pred.risk_index <= 1.0
        assert 0.0 <= pred.confidence <= 1.0
        assert pred.score_band in list(ScoreBand)

    def test_eligible_user_has_amount(self, api):
        resp = api.post("/api/ml/predict", json=_good_request())
        pred = CreditPrediction(**resp.json())
        if pred.eligible:
            assert pred.max_amount is not None
            assert pred.max_amount >= 100_000
            assert pred.recommended_product is not None

    def test_ineligible_user_no_amount(self, api):
        resp = api.post("/api/ml/predict", json=_bad_request())
        pred = CreditPrediction(**resp.json())
        if not pred.eligible:
            assert pred.max_amount is None
            assert pred.recommended_product is None

    def test_score_band_matches_p_default(self, api):
        """Score band thresholds must be consistent."""
        for body in [_good_request(), _bad_request(), _minimal_request()]:
            resp = api.post("/api/ml/predict", json=body)
            pred = CreditPrediction(**resp.json())
            if pred.p_default < 0.20:
                assert pred.score_band == ScoreBand.low_risk
            elif pred.p_default < 0.50:
                assert pred.score_band == ScoreBand.medium_risk
            else:
                assert pred.score_band == ScoreBand.high_risk

    def test_factors_present(self, api):
        resp = api.post("/api/ml/predict", json=_good_request())
        pred = CreditPrediction(**resp.json())
        assert len(pred.factors) > 0
        for f in pred.factors:
            assert f.name
            assert f.impact in ("positive", "negative")
            assert f.weight > 0

    def test_minimal_request_accepted(self, api):
        """Only demographic fields should be sufficient."""
        resp = api.post("/api/ml/predict", json=_minimal_request())
        assert resp.status_code == 200
        CreditPrediction(**resp.json())

    def test_rejects_missing_required_field(self, api):
        """Missing required field should return 422."""
        incomplete = {"declared_income": 1_000_000, "age": 30}
        resp = api.post("/api/ml/predict", json=incomplete)
        assert resp.status_code == 422

    def test_rejects_income_below_range(self, api):
        body = _good_request()
        body["declared_income"] = 100_000  # below 300K
        resp = api.post("/api/ml/predict", json=body)
        assert resp.status_code == 422

    def test_rejects_income_above_range(self, api):
        body = _good_request()
        body["declared_income"] = 20_000_000  # above 15M
        resp = api.post("/api/ml/predict", json=body)
        assert resp.status_code == 422

    def test_rejects_invalid_employment_type(self, api):
        body = _good_request()
        body["employment_type"] = "freelance"  # not in enum
        resp = api.post("/api/ml/predict", json=body)
        assert resp.status_code == 422

    def test_risk_monotonicity_income(self, api):
        """Higher income should result in lower or equal risk, all else equal."""
        base = _minimal_request()
        base["declared_income"] = 500_000
        r1 = CreditPrediction(**api.post("/api/ml/predict", json=base).json())
        base["declared_income"] = 5_000_000
        r2 = CreditPrediction(**api.post("/api/ml/predict", json=base).json())
        assert r2.p_default <= r1.p_default

    def test_risk_monotonicity_on_time(self, api):
        """Higher on_time_rate should result in lower risk."""
        base = _minimal_request()
        base["on_time_rate"] = 0.2
        r1 = CreditPrediction(**api.post("/api/ml/predict", json=base).json())
        base["on_time_rate"] = 0.95
        r2 = CreditPrediction(**api.post("/api/ml/predict", json=base).json())
        assert r2.p_default <= r1.p_default

    def test_banked_reduces_risk(self, api):
        """Being banked should reduce risk vs not banked."""
        base = _minimal_request()
        base["is_banked"] = False
        r1 = CreditPrediction(**api.post("/api/ml/predict", json=base).json())
        base["is_banked"] = True
        r2 = CreditPrediction(**api.post("/api/ml/predict", json=base).json())
        assert r2.p_default <= r1.p_default


@pytest.mark.contract
class TestScoreHistoryContract:
    """GET /api/ml/score-history/{client_id} must return list[ScoreEntry]."""

    def test_returns_list(self, api):
        resp = api.get("/api/ml/score-history/contract-test-001")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_entries_valid_schema(self, api):
        resp = api.get("/api/ml/score-history/contract-test-002")
        for entry in resp.json():
            se = ScoreEntry(**entry)
            assert 0.0 <= se.p_default <= 1.0
            assert 0.0 <= se.risk_index <= 1.0
            assert se.score_band in list(ScoreBand)
            assert isinstance(se.eligible, bool)
            # Date should be ISO format
            assert len(se.date) == 10  # YYYY-MM-DD


@pytest.mark.contract
class TestFeaturesSpecContract:
    """GET /api/ml/features-spec must return list[FeatureSpec]."""

    def test_returns_all_features(self, api):
        resp = api.get("/api/ml/features-spec")
        assert resp.status_code == 200
        specs = [FeatureSpec(**s) for s in resp.json()]
        names = {s.name for s in specs}
        # Must include all features from contract
        for feature_name in FEATURE_RANGES:
            assert feature_name in names, f"Missing feature: {feature_name}"

    def test_required_count(self, api):
        resp = api.get("/api/ml/features-spec")
        specs = [FeatureSpec(**s) for s in resp.json()]
        required = [s for s in specs if s.required]
        assert len(required) == 7  # 7 demographic features

    def test_feature_ranges_match_contract(self, api):
        resp = api.get("/api/ml/features-spec")
        specs = {s["name"]: s for s in resp.json()}
        for name, expected in FEATURE_RANGES.items():
            if "min" in expected:
                assert specs[name].get("range_min") == expected["min"], \
                    f"{name} range_min mismatch"
            if "max" in expected:
                assert specs[name].get("range_max") == expected["max"], \
                    f"{name} range_max mismatch"
            if "allowed" in expected:
                assert set(specs[name].get("allowed_values", [])) == set(expected["allowed"]), \
                    f"{name} allowed_values mismatch"


@pytest.mark.contract
class TestModelInfoContract:
    """GET /api/ml/model-info must return ModelInfo."""

    def test_returns_valid_schema(self, api):
        resp = api.get("/api/ml/model-info")
        assert resp.status_code == 200
        info = ModelInfo(**resp.json())
        assert info.model_type
        assert info.version
        assert info.base_rate > 0
        assert info.n_features > 0
        assert info.n_demographic_features + info.n_behavioral_features == info.n_features

    def test_feature_importances_present(self, api):
        resp = api.get("/api/ml/model-info")
        info = ModelInfo(**resp.json())
        assert len(info.feature_importances) > 0
        # Top feature should be on_time_rate
        top = max(info.feature_importances, key=info.feature_importances.get)
        assert top == "on_time_rate"


@pytest.mark.contract
class TestHealthContract:

    def test_health_returns_ok(self, api):
        resp = api.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
