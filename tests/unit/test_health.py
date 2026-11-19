"""Health endpoint smoke tests."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from clos.apps.api.main import app



@pytest.fixture
def client() -> Iterator[TestClient]:
    """Keep the app lifespan and async database engine on one event loop."""
    with TestClient(app) as test_client:
        yield test_client


def test_liveness(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}


def test_readiness(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_versioned_health_routes(client: TestClient) -> None:
    assert client.get("/v1/health/live").json() == {"status": "live"}
    assert client.get("/v1/health/ready").json() == {"status": "ready"}
