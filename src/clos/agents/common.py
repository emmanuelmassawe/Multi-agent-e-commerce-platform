"""Shared typed context and ports used by the four commerce agents."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AgentContext:
    tenant_id: UUID
    run_id: UUID
    customer_id: UUID | None = None


class AgentRunner(Protocol):
    async def run(self, message: str, context: AgentContext) -> str: ...


@dataclass(frozen=True, slots=True)
class StockLevel:
    product_id: UUID
    warehouse_id: UUID
    on_hand: int
    reserved: int
    average_daily_demand: float | None = None
    lead_time_days: float | None = None


class InventoryPort(Protocol):
    async def read_stock(self, tenant_id: UUID, product_id: UUID) -> list[StockLevel]: ...


@dataclass(frozen=True, slots=True)
class CompetitorPrice:
    source: str
    amount: float
    currency: str


class PricingPort(Protocol):
    async def fetch_competitor_prices(
        self, tenant_id: UUID, product_id: UUID
    ) -> list[CompetitorPrice]: ...


@dataclass(frozen=True, slots=True)
class PriceRule:
    min_margin: float | None = None
    floor: float | None = None
    ceiling: float | None = None
    approval_threshold: float | None = None
    stockout_markup: float | None = None


@dataclass(frozen=True, slots=True)
class Shipment:
    shipment_id: UUID
    status: str
    promised_at: str | None = None
    last_event: str | None = None


class LogisticsPort(Protocol):
    async def track(self, tenant_id: UUID, shipment_id: UUID) -> Shipment: ...


@dataclass(frozen=True, slots=True)
class RouteOption:
    carrier: str
    cost: float
    duration_hours: float


@dataclass(frozen=True, slots=True)
class RetrievedDocument:
    document_id: UUID
    text: str
    source: str


class SupportRetrievalPort(Protocol):
    async def search(
        self, tenant_id: UUID, customer_id: UUID, query: str, *, limit: int
    ) -> list[RetrievedDocument]: ...
