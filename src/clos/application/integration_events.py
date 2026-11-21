"""Minimized DTOs for authenticated integration events and read-only feeds."""

from decimal import Decimal
from typing import Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field


class OrderCreated(BaseModel):
    id: int = Field(gt=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    total_price: Decimal = Field(ge=0, max_digits=18, decimal_places=4)


class TrackingUpdate(BaseModel):
    shipment_id: UUID
    status: str = Field(min_length=1, max_length=32)
    occurred_at: AwareDatetime


class PriceObservation(BaseModel):
    listing_id: UUID
    price: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class IntegrationTransport(Protocol):
    async def send(self, url: str, data: bytes, headers: dict[str, str]) -> None: ...
    async def feed(self, url: str, token: str | None) -> bytes: ...
