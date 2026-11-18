"""Unit coverage for budgets, LLM fallback, and policy-gated typed tools."""

import asyncio
from uuid import uuid4

import pytest
from pydantic import BaseModel

from clos.agents.budgets import BudgetEnforcer, BudgetExceeded, BudgetLimits
from clos.agents.llm import FakeLLM, FallbackLLM, LLMRequest
from clos.agents.tools import (
    InMemoryIdempotencyStore,
    ToolContext,
    ToolInputError,
    ToolPolicyError,
    ToolRegistry,
    ToolSpec,
)
from clos.domain.identity import AutonomyMode, RiskLevel


def test_budget_enforcer_hard_stops_at_each_limit() -> None:
    budget = BudgetEnforcer(BudgetLimits(max_tokens=2, max_steps=1, max_tool_calls=1))
    budget.record_tokens(2)
    with pytest.raises(BudgetExceeded, match="token"):
        budget.record_tokens(1)
    budget.record_step()
    with pytest.raises(BudgetExceeded, match="step"):
        budget.record_step()
    budget.record_tool_call()
    with pytest.raises(BudgetExceeded, match="tool-call"):
        budget.record_tool_call()
    with pytest.raises(BudgetExceeded, match="wall-clock"):
        budget.check_time(1.0)


def test_fallback_llm_uses_fake_after_provider_failure() -> None:
    async def fail(_request: LLMRequest):
        raise RuntimeError("provider unavailable")

    async def scenario() -> None:
        from clos.agents.llm import ProviderLLMAdapter

        llm = FallbackLLM(ProviderLLMAdapter("primary", fail), FakeLLM())
        result = await llm.complete(
            LLMRequest(task="respond", prompt="hello", tenant_id="t", run_id="r")
        )
        assert result.model == "fake-deterministic"
        assert result.cost_usd == 0

    asyncio.run(scenario())


class Input(BaseModel):
    value: int


def test_typed_tool_validates_gates_risk_and_reuses_idempotent_result() -> None:
    async def scenario() -> None:
        calls = 0

        async def handler(data: BaseModel, _context: ToolContext) -> object:
            nonlocal calls
            calls += 1
            return {"doubled": data.value * 2}  # type: ignore[attr-defined]

        budget = BudgetEnforcer(BudgetLimits(max_tool_calls=2))
        registry = ToolRegistry(InMemoryIdempotencyStore(), budget)
        registry.register(ToolSpec("read_value", Input, RiskLevel.READ, handler))
        context = ToolContext(uuid4(), uuid4(), "request-1")
        with pytest.raises(ToolInputError):
            await registry.execute("read_value", {"value": "bad"}, context)
        first = await registry.execute("read_value", {"value": 4}, context)
        second = await registry.execute("read_value", {"value": 4}, context)
        assert first == second == {"doubled": 8}
        assert calls == 1

        async def write_handler(_data: BaseModel, _context: ToolContext) -> object:
            return {"written": True}

        registry.register(ToolSpec("update", Input, RiskLevel.WRITE_LOW, write_handler))
        with pytest.raises(ToolPolicyError):
            await registry.execute("update", {"value": 1}, context)
        permitted = ToolContext(
            context.tenant_id,
            context.run_id,
            "write-1",
            autonomy_mode=AutonomyMode.AUTONOMOUS,
            in_rule=True,
            kill_switch_active=True,
        )
        with pytest.raises(ToolPolicyError, match="kill switch"):
            await registry.execute("update", {"value": 1}, permitted)

        registry.register(
            ToolSpec("dangerous", Input, RiskLevel.WRITE_HIGH, write_handler)
        )
        with pytest.raises(ToolPolicyError, match="approved request"):
            await registry.execute("dangerous", {"value": 1}, context)
        approved = ToolContext(
            context.tenant_id,
            context.run_id,
            "high-1",
            approved=True,
            approval_id=uuid4(),
        )
        assert await registry.execute("dangerous", {"value": 1}, approved) == {"written": True}

    asyncio.run(scenario())


def test_typed_tool_retries_temporary_failure_then_succeeds() -> None:
    async def scenario() -> None:
        attempts = 0

        async def handler(_data: BaseModel, _context: ToolContext) -> object:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TimeoutError("temporary")
            return "ok"

        registry = ToolRegistry(
            InMemoryIdempotencyStore(),
            BudgetEnforcer(BudgetLimits()),
            jitter=lambda _low, _high: 0,
            sleep=lambda _delay: asyncio.sleep(0),
        )
        registry.register(ToolSpec("retry", Input, RiskLevel.READ, handler, max_retries=1))
        result = await registry.execute(
            "retry", {"value": 1}, ToolContext(uuid4(), uuid4(), "retry-1")
        )
        assert result == "ok"
        assert attempts == 2

    asyncio.run(scenario())
