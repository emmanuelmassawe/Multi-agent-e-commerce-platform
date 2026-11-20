"""Check the published operations and the access boundary used by all memory routes."""

from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from fastapi.testclient import TestClient

from clos.application.auth import Principal
from clos.apps.api.auth_routes import get_principal
from clos.apps.api.main import app
from clos.domain.identity import Role


def test_phase5_operation_contract() -> None:
    published = yaml.safe_load(Path("docs/api/openapi.yaml").read_text(encoding="utf8"))["paths"]
    actual = app.openapi()["paths"]
    expected = {
        ("/v1" + path, method)
        for path in published
        if "/memory" in path
        for method in published[path]
        if method in {"get", "post", "delete"}
    }
    assert expected == {
        (path, method) for path in actual if "/memory" in path for method in actual[path]
    }
    for path, method in expected:
        contract = published[path[3:]][method]
        route = actual[path][method]
        assert route["operationId"] == contract["operationId"]
        assert (set(contract["responses"]) & {"200", "202"}) == (
            set(route["responses"]) & {"200", "202"}
        )
        if any(
            p.get("$ref", "").endswith("/IdempotencyKey") for p in contract.get("parameters", [])
        ):
            assert any(
                p["name"] == "Idempotency-Key" and p["required"] for p in route["parameters"]
            )


@pytest.mark.parametrize(
    "principal",
    [
        Principal(uuid4(), uuid4(), Role.VIEWER, "viewer@example.invalid", frozenset({"*"})),
        Principal(uuid4(), uuid4(), Role.OWNER, "owner@example.invalid", frozenset({"read"})),
    ],
)
def test_private_export_requires_role_and_key_scope(principal: Principal) -> None:
    app.dependency_overrides[get_principal] = lambda: principal
    try:
        with TestClient(app) as client:
            response = client.get(f"/v1/customers/{uuid4()}/memory")
            assert response.status_code == 403
    finally:
        del app.dependency_overrides[get_principal]


def test_scrape_retrieval_metrics() -> None:
    with TestClient(app) as client:
        result = client.get("/metrics")
        assert result.status_code == 200
        assert "retrieval_latency_seconds_bucket" in result.text
        assert "retrieval_empty_total" in result.text
