"""Pricing recommendations constrained by explicit tenant price rules."""

from dataclasses import dataclass
from uuid import UUID

from clos.agents.common import AgentContext, CompetitorPrice, PriceRule, PricingPort
from clos.domain.identity import RiskLevel


@dataclass(frozen=True, slots=True)
class PriceRecommendation:
    recommended_price: float | None
    rationale: str
    approval_required: bool
    stockout_risk_considered: bool = False


class PricingAgent:
    def __init__(self, port: PricingPort) -> None:
        self.port = port

    async def fetch_competitor_prices(
        self, product_id: UUID, context: AgentContext
    ) -> list[CompetitorPrice]:
        return await self.port.fetch_competitor_prices(context.tenant_id, product_id)

    def compute_price_recommendation(
        self,
        *,
        current_price: float,
        cost: float,
        competitors: list[CompetitorPrice],
        rule: PriceRule,
        stockout_risk: bool = False,
    ) -> PriceRecommendation:
        if current_price <= 0 or cost < 0:
            raise ValueError("Price must be positive and cost cannot be negative")
        candidates = [price.amount for price in competitors if price.amount > 0]
        target = min(candidates) if candidates else current_price
        if stockout_risk and rule.stockout_markup is not None:
            if rule.stockout_markup < 0:
                raise ValueError("Stockout markup cannot be negative")
            target = max(target, current_price * (1 + rule.stockout_markup))
        floor = max(rule.floor or 0, cost * (1 + (rule.min_margin or 0)))
        ceiling = rule.ceiling
        if ceiling is not None and ceiling < floor:
            return PriceRecommendation(
                None,
                "Configured ceiling is below the cost and margin floor",
                True,
                stockout_risk,
            )
        target = max(floor, target)
        if ceiling is not None:
            target = min(ceiling, target)
        change_ratio = abs(target - current_price) / current_price
        approval = rule.approval_threshold is None or change_ratio > rule.approval_threshold
        rationale = "Competitor reference constrained by configured price rules"
        if stockout_risk:
            rationale += "; stockout risk considered using the configured stockout markup"
        return PriceRecommendation(target, rationale, approval, stockout_risk)

    def apply_price_change(self, recommendation: PriceRecommendation) -> dict[str, object]:
        return {
            "recommended_price": recommendation.recommended_price,
            "risk_level": RiskLevel.WRITE_HIGH.value,
            "approval_required": recommendation.approval_required,
            "executed": False,
        }


__all__ = ["PricingAgent", "PriceRecommendation"]
