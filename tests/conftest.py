"""Shared test fixtures for Helpyy Hand."""

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider that returns canned responses."""
    # TODO: create mock that returns predictable responses
    pass


@pytest.fixture
def mock_ml_client():
    """Mock ML client with configurable predictions."""
    # TODO: create mock with approve/reject scenarios
    pass


@pytest.fixture
def sample_user_state():
    """Sample user state for testing."""
    from backend.data.schemas import UserState
    return UserState(user_id="test-user-001", is_banked=False)
