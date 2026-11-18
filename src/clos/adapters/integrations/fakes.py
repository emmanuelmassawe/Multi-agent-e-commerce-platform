"""Deterministic integration fakes for the agent tools."""

from uuid import UUID

from clos.agents.common import (
    CompetitorPrice,
    RetrievedDocument,
    RouteOption,
    Shipment,
    StockLevel,
)


class FakeCommerce:
    def __init__(self) -> None:
        self.stock: dict[tuple[UUID, UUID], list[StockLevel]] = {}
        self.competitors: dict[tuple[UUID, UUID], list[CompetitorPrice]] = {}
        self.shipments: dict[tuple[UUID, UUID], Shipment] = {}
        self.documents: dict[tuple[UUID, UUID], list[RetrievedDocument]] = {}
        self.last_retrieval_scope: tuple[UUID, UUID] | None = None

    async def read_stock(self, tenant_id: UUID, product_id: UUID) -> list[StockLevel]:
        return list(self.stock.get((tenant_id, product_id), []))

    async def fetch_competitor_prices(
        self, tenant_id: UUID, product_id: UUID
    ) -> list[CompetitorPrice]:
        return list(self.competitors.get((tenant_id, product_id), []))

    async def track(self, tenant_id: UUID, shipment_id: UUID) -> Shipment:
        try:
            return self.shipments[(tenant_id, shipment_id)]
        except KeyError as exc:
            raise LookupError("Shipment not found in tenant scope") from exc

    async def search(
        self, tenant_id: UUID, customer_id: UUID, query: str, *, limit: int
    ) -> list[RetrievedDocument]:
        self.last_retrieval_scope = (tenant_id, customer_id)
        del query
        return list(self.documents.get((tenant_id, customer_id), []))[:limit]


__all__ = ["FakeCommerce", "RouteOption"]
