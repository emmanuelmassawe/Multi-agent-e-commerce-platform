"""Domain entity construction and safe defaults."""

from datetime import UTC, datetime
from decimal import Decimal

from clos.domain.entities import (
    AgentRun,
    ApprovalRequest,
    AuditLog,
    AutonomySetting,
    Carrier,
    CompetitorListing,
    Conversation,
    Customer,
    InventoryItem,
    Message,
    Order,
    PriceRule,
    PriceSnapshot,
    Product,
    Shipment,
    ShipmentEvent,
    Supplier,
    Tenant,
    TokenUsage,
    ToolCall,
    User,
    Warehouse,
)
from clos.domain.identity import AutonomyMode, Role
from clos.domain.ids import new_uuid7


def test_phase1_entities_are_framework_independent_and_default_to_shadow() -> None:
    entity_id = new_uuid7()
    tenant_id = new_uuid7()
    product_id = new_uuid7()
    warehouse_id = new_uuid7()
    customer_id = new_uuid7()
    order_id = new_uuid7()
    carrier_id = new_uuid7()
    shipment_id = new_uuid7()
    conversation_id = new_uuid7()
    run_id = new_uuid7()
    now = datetime.now(UTC)
    assert Tenant(entity_id, "shop", "Shop").id == entity_id
    assert User(entity_id, tenant_id, "owner@example.test", Role.OWNER).tenant_id == tenant_id
    assert Product(entity_id, tenant_id, "sku", "Product", "TZS").sku == "sku"
    assert Warehouse(entity_id, tenant_id, "Main", "TZ").region == "TZ"
    assert Supplier(entity_id, tenant_id, "Supplier").name == "Supplier"
    assert InventoryItem(entity_id, tenant_id, product_id, warehouse_id, 7).reserved_quantity == 0
    assert Order(entity_id, tenant_id, "pending", "TZS", Decimal("12.50")).total == Decimal("12.50")
    assert Carrier(entity_id, tenant_id, "Carrier").name == "Carrier"
    assert Shipment(entity_id, tenant_id, order_id, carrier_id, "pending").order_id == order_id
    assert ShipmentEvent(entity_id, tenant_id, shipment_id, "created", now).payload == {}
    assert PriceRule(entity_id, tenant_id, product_id, Decimal(1), Decimal(2), Decimal(".1"))
    assert PriceSnapshot(entity_id, tenant_id, product_id, Decimal(1), "TZS", now)
    assert CompetitorListing(entity_id, tenant_id, product_id, "source", Decimal(1), "TZS")
    assert Customer(entity_id, tenant_id, "Buyer").display_name == "Buyer"
    assert Conversation(entity_id, tenant_id, customer_id, "open").customer_id == customer_id
    assert Message(entity_id, tenant_id, conversation_id, "inbound", "hello").body == "hello"
    assert AgentRun(entity_id, tenant_id, "support", "queued").autonomy_mode == AutonomyMode.SHADOW
    assert AutonomySetting(entity_id, tenant_id, "support").mode == AutonomyMode.SHADOW
    assert ApprovalRequest(entity_id, tenant_id, run_id, "reorder", "pending").status == "pending"
    assert ToolCall(entity_id, tenant_id, run_id, "lookup", "complete").tool_name == "lookup"
    assert AuditLog(entity_id, tenant_id, None, "created", "product", None).action == "created"
    assert TokenUsage(entity_id, tenant_id, run_id, "fake", 1, 2).output_tokens == 2
