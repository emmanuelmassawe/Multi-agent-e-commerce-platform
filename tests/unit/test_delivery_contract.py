"""Exercise signatures and compare the published run and delivery operations."""

from pathlib import Path

import pytest
import yaml

from clos.application.delivery import signature, verified
from clos.apps.api.main import app


@pytest.mark.parametrize("stamp", ["", "abc", "0000000000001", "1301", "699", "９９９"])
def test_invalid_carrier_timestamp(stamp: str) -> None:
    payload = b"data"
    signed = signature("test", stamp, "event", payload)
    assert not verified("test", "carrier", signed, "event", stamp, payload, 1000)


def test_signed_carrier_inputs() -> None:
    signed = signature("test", "1000", "event", b"data")
    assert verified("test", "carrier", signed, "event", "1000", b"data", 1300)
    assert not verified("test", "carrier", signed, "other", "1000", b"data", 1300)
    assert not verified("test", "carrier", signed, "event", "1000", b"edited", 1300)
    assert not verified("test", "carrier", "", "event", "1000", b"data", 1300)


def test_delivery_operations_match_published_contract() -> None:
    paths = yaml.safe_load(Path("docs/api/openapi.yaml").read_text(encoding="utf8"))["paths"]
    actual = app.openapi()["paths"]
    for path, operations in paths.items():
        if not path.startswith(("/runs", "/dead-letters", "/webhooks")):
            continue
        for method, operation in operations.items():
            if method == "parameters":
                continue
            route = actual["/v1" + path][method]
            assert route["operationId"] == operation["operationId"]
            assert set(route["responses"]) & {"200", "202"} == set(operation["responses"]) & {
                "200",
                "202",
            }
            if method == "post" and not path.startswith("/webhooks"):
                assert any(
                    p["name"] == "Idempotency-Key" and p["required"] for p in route["parameters"]
                )
