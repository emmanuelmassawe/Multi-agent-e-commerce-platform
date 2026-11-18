"""Inventory agent tools and fake ports."""

from dataclasses import dataclass
from uuid import UUID

from clos.agents.common import AgentContext, InventoryPort
from clos.domain.identity import RiskLevel


@dataclass(frozen=True, slots=True)
class StockForecast:
    product_id: UUID
    available: int
    days_of_cover: float | None
    estimated_stockout_days: float | None


class InventoryAgent:
    def __init__(self, port: InventoryPort) -> None:
        self.port = port

    async def read_stock_levels(
        self, product_id: UUID, context: AgentContext
    ) -> list[dict[str, object]]:
        levels = await self.port.read_stock(context.tenant_id, product_id)
        return [
            {
                "product_id": str(item.product_id),
                "warehouse_id": str(item.warehouse_id),
                "on_hand": item.on_hand,
                "reserved": item.reserved,
                "available": max(0, item.on_hand - item.reserved),
            }
            for item in levels
        ]

    async def forecast_stockout(
        self, product_id: UUID, context: AgentContext
    ) -> list[StockForecast]:
        levels = await self.port.read_stock(context.tenant_id, product_id)
        result = []
        for item in levels:
            available = max(0, item.on_hand - item.reserved)
            cover = available / item.average_daily_demand if item.average_daily_demand else None
            result.append(StockForecast(product_id, available, cover, cover))
        return result

    async def propose_reorder(
        self, product_id: UUID, quantity: int, context: AgentContext
    ) -> dict[str, object]:
        if quantity <= 0:
            raise ValueError("Reorder quantity must be positive")
        return {
            "product_id": str(product_id),
            "quantity": quantity,
            "risk_level": RiskLevel.WRITE_HIGH.value,
            "approval_required": True,
            "executed": False,
            "tenant_id": str(context.tenant_id),
        }


__all__ = ["InventoryAgent", "StockForecast"]
