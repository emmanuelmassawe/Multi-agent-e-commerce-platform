"""Identifier generation helpers."""

from __future__ import annotations

import secrets
import time
from uuid import UUID


def new_uuid7() -> UUID:
    """Return a time-ordered UUIDv7 without relying on a newer Python runtime."""
    timestamp_ms = time.time_ns() // 1_000_000
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (
        ((timestamp_ms & 0xFFFFFFFFFFFF) << 80)
        | (0x7 << 76)
        | (random_a << 64)
        | (0b10 << 62)
        | random_b
    )
    return UUID(int=value)

