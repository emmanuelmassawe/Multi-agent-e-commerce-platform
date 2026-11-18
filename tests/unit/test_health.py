"""Health endpoint smoke tests."""

from fastapi.testclient import TestClient

from clos.apps.api.main import app

client = TestClient(app)


def test_liveness() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}


def test_readiness() -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_versioned_health_routes() -> None:
    assert client.get("/v1/health/live").json() == {"status": "live"}
    assert client.get("/v1/health/ready").json() == {"status": "ready"}
