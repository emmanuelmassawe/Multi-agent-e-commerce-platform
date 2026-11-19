"""SQLAlchemy persistence models; domain entities remain framework independent."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from clos.domain.ids import new_uuid7


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(UTC)


class Base(AsyncAttrs, DeclarativeBase):
    """Base for SQLAlchemy's async ORM models."""


class TenantScoped:
    """Common identity and tenant ownership fields for tenant-owned rows."""

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid7)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (UniqueConstraint("slug", name="uq_tenants_slug"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid7)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class User(TenantScoped, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ApiKey(TenantScoped, Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_api_keys_idempotency"),
    )

    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(TenantScoped, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_refresh_tokens_hash"),)

    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Product(TenantScoped, Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("tenant_id", "sku", name="uq_products_tenant_sku"),)

    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Warehouse(TenantScoped, Base):
    __tablename__ = "warehouses"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")


class Supplier(TenantScoped, Base):
    __tablename__ = "suppliers"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(320))
    lead_time_days: Mapped[int | None] = mapped_column(Integer)


class InventoryItem(TenantScoped, Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "product_id", "warehouse_id", name="uq_inventory_product_warehouse"
        ),
        Index("ix_inventory_tenant_product", "tenant_id", "product_id"),
    )

    product_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("products.id"), nullable=False)
    warehouse_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("warehouses.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Customer(TenantScoped, Base):
    __tablename__ = "customers"

    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))


class Order(TenantScoped, Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_ref", name="uq_orders_tenant_external_ref"),
    )

    external_ref: Mapped[str | None] = mapped_column(String(120))
    customer_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("customers.id"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)


class Carrier(TenantScoped, Base):
    __tablename__ = "carriers"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_carriers_tenant_name"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    supported_regions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class Shipment(TenantScoped, Base):
    __tablename__ = "shipments"

    order_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("orders.id"), nullable=False)
    carrier_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("carriers.id"))
    tracking_number: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    promised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ShipmentEvent(TenantScoped, Base):
    __tablename__ = "shipment_events"
    __table_args__ = (Index("ix_shipment_events_tenant_shipment", "tenant_id", "shipment_id"),)

    shipment_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("shipments.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class PriceRule(TenantScoped, Base):
    __tablename__ = "price_rules"

    product_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("products.id"), nullable=False)
    min_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    max_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    min_margin: Mapped[Decimal] = mapped_column(Numeric(8, 5), nullable=False)
    max_change_per_day: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))


class PriceSnapshot(TenantScoped, Base):
    __tablename__ = "price_snapshots"
    __table_args__ = (Index("ix_price_snapshots_tenant_product", "tenant_id", "product_id"),)

    product_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("products.id"), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CompetitorListing(TenantScoped, Base):
    __tablename__ = "competitor_listings"

    product_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("products.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(240))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Conversation(TenantScoped, Base):
    __tablename__ = "conversations"

    customer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("customers.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")


class Message(TenantScoped, Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_tenant_conversation", "tenant_id", "conversation_id"),)

    conversation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


class AgentRun(TenantScoped, Base):
    __tablename__ = "agent_runs"

    agent_name: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    autonomy_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="shadow")
    explanation: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class AutonomySetting(TenantScoped, Base):
    __tablename__ = "autonomy_settings"
    __table_args__ = (UniqueConstraint("tenant_id", "agent_name", name="uq_autonomy_tenant_agent"),)

    agent_name: Mapped[str] = mapped_column(String(80), nullable=False)
    mode: Mapped[str] = mapped_column(String(24), nullable=False, default="shadow")
    updated_by: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))


class ApprovalRequest(TenantScoped, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "agent_run_id",
            "action",
            "tool_idempotency_key",
            name="uq_approvals_run_action_idempotency",
        ),
    )

    agent_run_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("agent_runs.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    tool_idempotency_key: Mapped[str | None] = mapped_column(String(200))
    risk_level: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    requested_by: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    decided_by: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolCall(TenantScoped, Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "agent_run_id",
            "tool_name",
            "idempotency_key",
            name="uq_tool_calls_run_tool_idempotency",
        ),
    )

    agent_run_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("agent_runs.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    input_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class AuditLog(TenantScoped, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_tenant_created", "tenant_id", "created_at"),)

    actor_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class TokenUsage(TenantScoped, Base):
    __tablename__ = "token_usage"

    agent_run_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("agent_runs.id"), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))


class MemoryDocument(TenantScoped, Base):
    __tablename__ = "memory_documents"
    customer_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("customers.id"))
    source: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)


class MemoryChunk(TenantScoped, Base):
    __tablename__ = "memory_chunks"
    document_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("memory_documents.id", ondelete="CASCADE"), index=True
    )
    body: Mapped[str] = mapped_column(Text)


class MemoryJob(TenantScoped, Base):
    __tablename__ = "memory_jobs"
    operation: Mapped[str] = mapped_column(String(20))
    subject_id: Mapped[UUID | None] = mapped_column(Uuid)
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")


TENANT_TABLE_NAMES = tuple(
    table.name for table in Base.metadata.sorted_tables if table.name != "tenants"
)
