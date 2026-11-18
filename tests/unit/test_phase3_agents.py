import asyncio
from uuid import uuid4

import pytest

from clos.adapters.integrations.fakes import FakeCommerce
from clos.agents.common import (
    AgentContext,
    CompetitorPrice,
    PriceRule,
    RetrievedDocument,
    RouteOption,
    Shipment,
    StockLevel,
)
from clos.agents.inventory import InventoryAgent, StockForecast
from clos.agents.logistics import LogisticsAgent
from clos.agents.pricing import PricingAgent
from clos.agents.support import SupportAgent


def test_inventory_tools_are_tenant_scoped_and_reorder_is_proposal() -> None:
    fake = FakeCommerce()
    tenant, other_tenant, product, warehouse = uuid4(), uuid4(), uuid4(), uuid4()
    fake.stock[(tenant, product)] = [StockLevel(product, warehouse, 12, 3, 3.0, 5.0)]
    fake.stock[(other_tenant, product)] = [StockLevel(product, warehouse, 900, 0)]
    agent = InventoryAgent(fake)
    context = AgentContext(tenant, uuid4())

    async def run_tools() -> tuple[list[dict[str, object]], list[StockForecast], dict[str, object]]:
        return (
            await agent.read_stock_levels(product, context),
            await agent.forecast_stockout(product, context),
            await agent.propose_reorder(product, 20, context),
        )

    levels, forecast, proposal = asyncio.run(run_tools())

    assert levels[0]["available"] == 9
    assert forecast[0].days_of_cover == 3
    assert proposal["approval_required"] is True
    assert proposal["executed"] is False


def test_pricing_respects_floor_ceiling_and_missing_threshold() -> None:
    agent = PricingAgent(FakeCommerce())
    suggestion = agent.compute_price_recommendation(
        current_price=20,
        cost=10,
        competitors=[CompetitorPrice("market-a", 12, "USD")],
        rule=PriceRule(min_margin=0.5, floor=11, ceiling=30),
    )
    assert suggestion.recommended_price == 15
    assert suggestion.approval_required is True
    assert agent.apply_price_change(suggestion)["executed"] is False
    impossible = agent.compute_price_recommendation(
        current_price=20, cost=10, competitors=[], rule=PriceRule(min_margin=0.5, ceiling=12)
    )
    assert impossible.recommended_price is None


def test_stockout_signal_flows_into_pricing_only_with_explicit_markup_rule() -> None:
    recommendation = PricingAgent(FakeCommerce()).compute_price_recommendation(
        current_price=20,
        cost=10,
        competitors=[CompetitorPrice("market-a", 16, "USD")],
        rule=PriceRule(min_margin=0.2, stockout_markup=0.1),
        stockout_risk=True,
    )
    assert recommendation.recommended_price == 22
    assert recommendation.stockout_risk_considered is True
    assert recommendation.approval_required is True


def test_logistics_delay_requires_policy_and_cross_agent_notice_is_draft() -> None:
    fake = FakeCommerce()
    tenant, customer_id, shipment_id = uuid4(), uuid4(), uuid4()
    shipment = Shipment(shipment_id, "in_transit", "2026-11-01T00:00:00Z", "Departed hub")
    fake.shipments[(tenant, shipment_id)] = shipment
    fake.documents[(tenant, customer_id)] = [
        RetrievedDocument(uuid4(), "We are checking your delivery.", "faq")
    ]
    logistics = LogisticsAgent(fake)
    support = SupportAgent(fake)
    context = AgentContext(tenant, uuid4(), customer_id)

    tracked = asyncio.run(logistics.track_shipment(shipment_id, context))
    unknown_rule = logistics.detect_delay(tracked)
    late = logistics.detect_delay(tracked, now="2026-11-02T00:00:00Z")
    draft = asyncio.run(support.answer_customer("Where is my parcel?", context))

    assert unknown_rule.delayed is None
    assert late.delayed is True
    assert draft["sent"] is False
    assert fake.last_retrieval_scope == (tenant, customer_id)


def test_support_retrieval_cannot_cross_tenant_or_customer_scope() -> None:
    fake = FakeCommerce()
    tenant, another_tenant, customer, another_customer = uuid4(), uuid4(), uuid4(), uuid4()
    fake.documents[(tenant, customer)] = [RetrievedDocument(uuid4(), "own order", "order")]
    fake.documents[(tenant, another_customer)] = [
        RetrievedDocument(uuid4(), "other customer", "order")
    ]
    fake.documents[(another_tenant, customer)] = [
        RetrievedDocument(uuid4(), "other tenant", "policy")
    ]
    agent = SupportAgent(fake)

    answer = asyncio.run(agent.answer_customer("status", AgentContext(tenant, uuid4(), customer)))
    assert "own order" in str(answer["answer"])
    assert "other customer" not in str(answer)
    assert "other tenant" not in str(answer)
    with pytest.raises(ValueError, match="Customer-scoped"):
        asyncio.run(agent.answer_customer("status", AgentContext(tenant, uuid4())))


def test_logistics_route_selection_uses_real_cost_then_duration_ordering() -> None:
    agent = LogisticsAgent(FakeCommerce())
    options = [
        RouteOption("slow", 5, 48),
        RouteOption("fast", 8, 12),
        RouteOption("same-cost", 5, 20),
    ]
    assert agent.plan_route(options) == options[2]
    assert agent.plan_route([]) is None
