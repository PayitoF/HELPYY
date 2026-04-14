"""Contract tests — validate that the ML service meets the new MLRepo API contract.

Run against:
    - Mock server (local dev):  pytest tests/contract/ -v -m contract
    - Real ML service (prod):   ML_SERVICE_URL=https://ml-scoring.internal pytest tests/contract/ -v -m contract
"""

import os

import pytest
from fastapi.testclient import TestClient

from backend.ml_client.mock_server import app as mock_app
from backend.ml_client.schemas import (
    HealthResponse,
    ModelInfoResponse,
    RiskRequest,
    RiskResponse,
)


def _get_client():
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


def _good_user() -> dict:
    return RiskRequest(
        declared_income=5_000_000, is_banked=1, employment_type="formal",
        age=35, city_type="urban", total_sessions=15, pct_conversion=0.8,
        tx_income_pct=0.6, payments_count=20, on_time_rate=0.95,
        overdue_rate=0.02, avg_decision_score=0.85,
    ).model_dump()


def _bad_user() -> dict:
    return RiskRequest(
        declared_income=300_000, is_banked=0, employment_type="informal",
        age=19, city_type="rural", total_sessions=1, pct_conversion=0.05,
        tx_income_pct=0.1, payments_count=2, on_time_rate=0.1,
        overdue_rate=0.8, avg_decision_score=0.15,
    ).model_dump()


@pytest.mark.contract
class TestRiskScore:
    """POST /risk-score contract."""

    def test_returns_valid_schema(self, api):
        resp = api.post("/risk-score", json=_good_user())
        assert resp.status_code == 200
        r = RiskResponse(**resp.json())
        assert 0.0 <= r.probability_of_default <= 1.0
        assert r.risk_category in ("LOW", "MEDIUM", "HIGH")
        assert r.decision in ("APPROVE", "REVIEW", "REJECT")
        assert isinstance(r.top_features, list) and len(r.top_features) > 0

    def test_good_user_approved(self, api):
        resp = api.post("/risk-score", json=_good_user())
        r = RiskResponse(**resp.json())
        assert r.decision == "APPROVE"

    def test_bad_user_not_approved(self, api):
        resp = api.post("/risk-score", json=_bad_user())
        r = RiskResponse(**resp.json())
        assert r.decision in ("REVIEW", "REJECT")

    def test_risk_category_thresholds(self, api):
        for body in [_good_user(), _bad_user()]:
            resp = api.post("/risk-score", json=body)
            r = RiskResponse(**resp.json())
            p = r.probability_of_default
            if p < 0.30:
                assert r.risk_category == "LOW"
            elif p < 0.60:
                assert r.risk_category == "MEDIUM"
            else:
                assert r.risk_category == "HIGH"

    def test_decision_thresholds(self, api):
        for body in [_good_user(), _bad_user()]:
            resp = api.post("/risk-score", json=body)
            r = RiskResponse(**resp.json())
            p = r.probability_of_default
            if p < 0.40:
                assert r.decision == "APPROVE"
            elif p < 0.65:
                assert r.decision == "REVIEW"
            else:
                assert r.decision == "REJECT"

    def test_missing_required_field_returns_422(self, api):
        incomplete = {"declared_income": 1_000_000, "age": 30}
        resp = api.post("/risk-score", json=incomplete)
        assert resp.status_code == 422

    def test_deterministic(self, api):
        body = _good_user()
        r1 = api.post("/risk-score", json=body).json()
        r2 = api.post("/risk-score", json=body).json()
        assert r1 == r2


@pytest.mark.contract
class TestHealth:
    """GET /health contract."""

    def test_returns_ok_with_model_loaded(self, api):
        resp = api.get("/health")
        assert resp.status_code == 200
        h = HealthResponse(**resp.json())
        assert h.status == "ok"
        assert h.model_loaded is True
        assert isinstance(h.model_path, str) and len(h.model_path) > 0


@pytest.mark.contract
class TestModelInfo:
    """GET /model-info contract."""

    def test_returns_valid_schema_with_top_features(self, api):
        resp = api.get("/model-info")
        assert resp.status_code == 200
        info = ModelInfoResponse(**resp.json())
        assert isinstance(info.top_features, list) and len(info.top_features) > 0
        assert isinstance(info.selected_training_features, list)
        assert info.model_name
        assert info.training_mode
