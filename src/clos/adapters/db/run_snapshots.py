"""Read-only, tenant-scoped operational snapshots for background graph runs."""

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clos.adapters.db.models import (
    AutonomySetting,
    CompetitorListing,
    InventoryItem,
    Shipment,
    utc_now,
)
from clos.adapters.db.session import tenant_session
from clos.adapters.db.tool_idempotency import SQLToolIdempotencyStore
from clos.agents.budgets import BudgetEnforcer, BudgetLimits
from clos.agents.common import AgentContext, AgentRunner
from clos.agents.tools import ToolContext, ToolRegistry, ToolSpec
from clos.domain.identity import RiskLevel


class SnapshotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SnapshotRunner:
    def __init__(
        self, name: str, sessions: async_sessionmaker[AsyncSession], registry: ToolRegistry
    ) -> None:
        self.name = name
        self.sessions = sessions
        self.registry = registry
        self.tool = f"read_{name}_snapshot"
        registry.register(ToolSpec(self.tool, SnapshotInput, RiskLevel.READ, self.read))

    async def read(self, _: BaseModel, context: ToolContext) -> object:
        async with tenant_session(self.sessions, context.tenant_id) as db:
            if self.name == "inventory":
                count = await db.scalar(
                    select(func.count())
                    .select_from(InventoryItem)
                    .where(
                        InventoryItem.tenant_id == context.tenant_id,
                        InventoryItem.quantity <= InventoryItem.reserved_quantity,
                    )
                )
                return {"stock_positions_without_available_units": count}
            if self.name == "pricing":
                count = await db.scalar(
                    select(func.count())
                    .select_from(CompetitorListing)
                    .where(CompetitorListing.tenant_id == context.tenant_id)
                )
                return {"recorded_competitor_listings": count}
            count = await db.scalar(
                select(func.count())
                .select_from(Shipment)
                .where(
                    Shipment.tenant_id == context.tenant_id,
                    Shipment.promised_at < utc_now(),
                    Shipment.status.not_in(["delivered", "cancelled"]),
                )
            )
            return {"open_shipments_past_promised_time": count}

    async def run(self, message: str, context: AgentContext) -> str:
        async with tenant_session(self.sessions, context.tenant_id) as db:
            mode = await db.scalar(
                select(AutonomySetting.mode).where(
                    AutonomySetting.tenant_id == context.tenant_id,
                    AutonomySetting.agent_name == self.name,
                )
            )
        if mode == "off":
            return f"{self.name} agent disabled."
        result = await self.registry.execute(
            self.tool, {}, ToolContext(context.tenant_id, context.run_id, "snapshot")
        )
        return f"Recorded {self.name} snapshot: {result}"


def runners(sessions: async_sessionmaker[AsyncSession]) -> dict[str, AgentRunner]:
    registry = ToolRegistry(SQLToolIdempotencyStore(sessions), BudgetEnforcer(BudgetLimits()))
    return {
        name: SnapshotRunner(name, sessions, registry)
        for name in ("inventory", "pricing", "logistics")
    }
