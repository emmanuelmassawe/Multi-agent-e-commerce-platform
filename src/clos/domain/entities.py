"""Pure domain entities. Persistence and web frameworks stay outside this module."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from clos.domain.identity import AutonomyMode, Role


@dataclass(frozen=True, slots=True)
class Tenant:
    id: UUID
    slug: str
    name: str


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    tenant_id: UUID
    email: str
    role: Role


@dataclass(frozen=True, slots=True)
class Product:
    id: UUID
    tenant_id: UUID
    sku: str
    name: str
    currency: str


@dataclass(frozen=True, slots=True)
class Warehouse:
    id: UUID
    tenant_id: UUID
    name: str
    region: str


@dataclass(frozen=True, slots=True)
class Supplier:
    id: UUID
    tenant_id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class InventoryItem:
    id: UUID
    tenant_id: UUID
    product_id: UUID
    warehouse_id: UUID
    quantity: int
    reserved_quantity: int = 0


@dataclass(frozen=True, slots=True)
class Order:
    id: UUID
    tenant_id: UUID
    status: str
    currency: str
    total: Decimal


@dataclass(frozen=True, slots=True)
class Carrier:
    id: UUID
    tenant_id: UUID
    name: str


@dataclass(frozen=True, slots=True)
class Shipment:
    id: UUID
    tenant_id: UUID
    order_id: UUID
    carrier_id: UUID | None
    status: str
    promised_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ShipmentEvent:
    id: UUID
    tenant_id: UUID
    shipment_id: UUID
    event_type: str
    occurred_at: datetime
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PriceRule:
    id: UUID
    tenant_id: UUID
    product_id: UUID
    min_price: Decimal
    max_price: Decimal
    min_margin: Decimal


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    id: UUID
    tenant_id: UUID
    product_id: UUID
    price: Decimal
    currency: str
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class CompetitorListing:
    id: UUID
    tenant_id: UUID
    product_id: UUID
    source: str
    price: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class Customer:
    id: UUID
    tenant_id: UUID
    display_name: str
    email: str | None = None


@dataclass(frozen=True, slots=True)
class Conversation:
    id: UUID
    tenant_id: UUID
    customer_id: UUID
    status: str


@dataclass(frozen=True, slots=True)
class Message:
    id: UUID
    tenant_id: UUID
    conversation_id: UUID
    direction: str
    body: str


@dataclass(frozen=True, slots=True)
class AgentRun:
    id: UUID
    tenant_id: UUID
    agent_name: str
    status: str
    autonomy_mode: AutonomyMode = AutonomyMode.SHADOW


@dataclass(frozen=True, slots=True)
class AutonomySetting:
    id: UUID
    tenant_id: UUID
    agent_name: str
    mode: AutonomyMode = AutonomyMode.SHADOW
    updated_by: UUID | None = None


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    id: UUID
    tenant_id: UUID
    agent_run_id: UUID
    action: str
    status: str


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: UUID
    tenant_id: UUID
    agent_run_id: UUID
    tool_name: str
    status: str


@dataclass(frozen=True, slots=True)
class AuditLog:
    id: UUID
    tenant_id: UUID
    actor_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID | None


@dataclass(frozen=True, slots=True)
class TokenUsage:
    id: UUID
    tenant_id: UUID
    agent_run_id: UUID
    model: str
    input_tokens: int
    output_tokens: int
