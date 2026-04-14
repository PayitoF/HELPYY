"""FastAPI dependency injection."""

from backend.llm.config import get_llm_provider
from backend.ml_client.client import MLClient
from backend.agents.orchestrator import Orchestrator


def get_orchestrator() -> Orchestrator:
    """Provide an Orchestrator instance with its dependencies."""
    # TODO: wire up LLM provider, ML client, and agents
    pass


def get_ml_client() -> MLClient:
    """Provide an MLClient instance."""
    # TODO: read ML_SERVICE_URL from env
    pass
