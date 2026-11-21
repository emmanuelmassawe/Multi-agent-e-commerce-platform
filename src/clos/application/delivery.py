"""Event instrumentation, webhook authentication and durable command identity."""

import base64
import hashlib
import hmac
import json
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

EventSink = Callable[[str, dict[str, Any]], Awaitable[None]]
events: ContextVar[EventSink | None] = ContextVar("run_events", default=None)


async def emit(name: str, **data: Any) -> None:
    sink = events.get()
    if sink:
        await sink(name, data)


class JobConflict(ValueError):
    pass


def fingerprint(data: object) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def signature(secret: str, timestamp: str, event_id: str, body: bytes) -> str:
    signed = timestamp.encode() + b"." + event_id.encode() + b"." + body
    return hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


def verified(
    secret: str, source: str, supplied: str, event_id: str, timestamp: str, body: bytes, now: int
) -> bool:
    if not secret or not supplied or not event_id or len(event_id) > 200:
        return False
    if source == "shopify":
        expected = base64.b64encode(hmac.digest(secret.encode(), body, "sha256")).decode()
    else:
        if not timestamp.isascii() or not timestamp.isdecimal() or len(timestamp) > 12:
            return False
        if abs(now - int(timestamp)) > 300:
            return False
        expected = signature(secret, timestamp, event_id, body)
    return hmac.compare_digest(expected.encode(), supplied.encode())
