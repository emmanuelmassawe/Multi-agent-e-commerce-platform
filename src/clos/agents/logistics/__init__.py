"""Shipment visibility and route planning based on supplied service choices."""

from dataclasses import dataclass
from uuid import UUID

from clos.agents.common import AgentContext, LogisticsPort, RouteOption, Shipment
from clos.domain.identity import RiskLevel


@dataclass(frozen=True, slots=True)
class DelayAssessment:
    delayed: bool | None
    reason: str


class LogisticsAgent:
    def __init__(self, port: LogisticsPort) -> None:
        self.port = port

    async def track_shipment(self, shipment_id: UUID, context: AgentContext) -> Shipment:
        return await self.port.track(context.tenant_id, shipment_id)

    def detect_delay(self, shipment: Shipment, *, now: str | None = None) -> DelayAssessment:
        if shipment.promised_at is None or now is None:
            return DelayAssessment(
                None, "Promised delivery time or comparison time was not supplied"
            )
        return DelayAssessment(
            now > shipment.promised_at and shipment.status.lower() != "delivered",
            "Compared supplied timestamps and delivery status",
        )

    def plan_route(self, options: list[RouteOption]) -> RouteOption | None:
        if not options:
            return None
        return min(options, key=lambda option: (option.cost, option.duration_hours))

    def rebook_shipment(self, shipment_id: UUID, option: RouteOption) -> dict[str, object]:
        return {
            "shipment_id": str(shipment_id),
            "carrier": option.carrier,
            "cost": option.cost,
            "risk_level": RiskLevel.WRITE_HIGH.value,
            "approval_required": True,
            "executed": False,
        }


__all__ = ["LogisticsAgent", "DelayAssessment"]
