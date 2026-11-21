"""Only operator-configured HTTPS destinations reach this adapter."""

import json
import time
from typing import Any
from uuid import UUID

import httpx

from clos.application.delivery import signature
from clos.application.integration_events import IntegrationTransport
from clos.config import IntegrationBinding


class HttpTransport:
    async def send(self, url: str, data: bytes, headers: dict[str, str]) -> None:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            async with client.stream("POST", url, content=data, headers=headers) as response:
                response.raise_for_status()

    async def feed(self, url: str, token: str | None) -> bytes:
        headers = {"Authorization": "Bearer " + token} if token else {}
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            async with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                body = bytearray()
                async for block in response.aiter_bytes():
                    body.extend(block)
                    if len(body) > 1_000_000:
                        raise ValueError("Integration feed exceeds size limit")
                return bytes(body)


async def deliver(
    transport: IntegrationTransport,
    binding: IntegrationBinding,
    tenant: UUID,
    event_id: UUID,
    payload: dict[str, Any],
) -> None:
    if not binding.outbound_url or not binding.outbound_secret:
        raise ValueError("Outbound subscriber is not configured")
    data = json.dumps(
        {**payload, "tenant_id": str(tenant), "event_id": str(event_id)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    stamp = str(int(time.time()))
    signed = signature(binding.outbound_secret.get_secret_value(), stamp, str(event_id), data)
    await transport.send(
        binding.outbound_url,
        data,
        {
            "Content-Type": "application/json",
            "X-CLOS-Event-Id": str(event_id),
            "X-CLOS-Timestamp": stamp,
            "X-CLOS-Signature": signed,
            "Idempotency-Key": str(event_id),
        },
    )
