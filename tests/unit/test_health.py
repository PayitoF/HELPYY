"""Test health endpoint."""


def test_health_endpoint(client):
    """GET /health returns 200 with expected body."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "helpyy-hand-api"
