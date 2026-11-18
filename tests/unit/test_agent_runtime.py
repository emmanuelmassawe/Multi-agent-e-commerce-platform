"""Unit coverage for budgets, LLM fallback, and policy-gated typed tools."""

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from clos.adapters.llm.factory import build_worker_llm
from clos.adapters.llm.gemini import (
    GeminiAPIAdapter,
    GeminiProviderUnavailable,
    KeyFallbackLLM,
    minimize_prompt,
)
from clos.adapters.llm.providers import FakeLLM, FallbackLLM, ProviderLLMAdapter
from clos.agents.budgets import BudgetEnforcer, BudgetExceeded, BudgetLimits
from clos.agents.tools import (
    ApprovalVerifierPort,
    InMemoryIdempotencyStore,
    ToolContext,
    ToolIdempotencyConflict,
    ToolInputError,
    ToolPolicyError,
    ToolRegistry,
    ToolSpec,
)
from clos.application.llm import LLMRequest, LLMResponse
from clos.config import Settings
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
    wall_budget = BudgetEnforcer(BudgetLimits(max_wall_seconds=1))
    with pytest.raises(BudgetExceeded, match="wall-clock"):
        wall_budget.check_time(1.0)


def test_fallback_llm_uses_fake_after_provider_failure() -> None:
    async def fail(_request: LLMRequest) -> LLMResponse:
        raise RuntimeError("provider unavailable")

    async def scenario() -> None:
        llm = FallbackLLM(ProviderLLMAdapter("primary", fail), FakeLLM())
        result = await llm.complete(
            LLMRequest(task="respond", prompt="hello", tenant_id="t", run_id="r")
        )
        assert result.model == "fake-deterministic"
        assert result.cost_usd == 0

    asyncio.run(scenario())


def test_gemini_key_pool_falls_back_without_exposing_provider_details() -> None:
    async def scenario() -> None:
        pool = KeyFallbackLLM((FakeLLM(fail=True), FakeLLM(model="fallback-key")))
        result = await pool.complete(
            LLMRequest(task="respond", prompt="hello", tenant_id="t", run_id="r")
        )
        assert result.model == "fallback-key"

        failed_pool = KeyFallbackLLM((FakeLLM(fail=True), FakeLLM(fail=True)))
        with pytest.raises(GeminiProviderUnavailable, match="2 configured Gemini keys"):
            await failed_pool.complete(
                LLMRequest(task="respond", prompt="hello", tenant_id="t", run_id="r")
            )

    asyncio.run(scenario())


def test_gemini_prompt_minimization_redacts_common_direct_identifiers() -> None:
    result = minimize_prompt(
        "Email jane.doe@example.com or call +255 712 345 678; api_key=do-not-send-this"
    )
    assert "jane.doe@example.com" not in result
    assert "+255 712 345 678" not in result
    assert "do-not-send-this" not in result
    assert "[EMAIL]" in result
    assert "[PHONE_OR_NUMBER]" in result
    assert "[CREDENTIAL]" in result


def test_gemini_adapter_passes_bounded_redacted_prompt_and_records_usage() -> None:
    class FakeGeminiClient:
        def __init__(self) -> None:
            self.aio = self
            self.models = self
            self.contents = ""
            self.requested_model = ""

        async def generate_content(
            self, *, model: str, contents: str, config: object
        ) -> SimpleNamespace:
            self.contents = contents
            self.requested_model = model
            return SimpleNamespace(
                text="safe response",
                model_version="gemini-test",
                usage_metadata=SimpleNamespace(prompt_token_count=9, candidates_token_count=2),
            )

        async def aclose(self) -> None:
            return None

    async def scenario() -> None:
        client = FakeGeminiClient()
        adapter = GeminiAPIAdapter(cast(Any, client), "gemini-test-config")
        result = await adapter.complete(
            LLMRequest(
                task="respond",
                prompt="Contact jane.doe@example.com",
                tenant_id="tenant-id",
                run_id="run-id",
                max_output_tokens=12,
            )
        )
        assert client.requested_model == "gemini-test-config"
        assert "jane.doe@example.com" not in client.contents
        assert "[EMAIL]" in client.contents
        assert result.model == "gemini-test"
        assert result.input_tokens == 9
        assert result.output_tokens == 2
        assert result.cost_usd is None

    asyncio.run(scenario())


def test_worker_llm_uses_fake_only_in_local_modes_and_requires_a_production_key() -> None:
    local = build_worker_llm(
        Settings(app_env="local", gemini_api_key=None, gemini_fallback_api_keys=None)
    )
    assert isinstance(local, FakeLLM)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        build_worker_llm(
            Settings(app_env="production", gemini_api_key=None, gemini_fallback_api_keys=None)
        )


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
        with pytest.raises(ToolIdempotencyConflict):
            await registry.execute("read_value", {"value": 5}, context)
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

        registry.register(ToolSpec("dangerous", Input, RiskLevel.WRITE_HIGH, write_handler))
        with pytest.raises(ToolPolicyError, match="approved request"):
            await registry.execute("dangerous", {"value": 1}, context)
        approved = ToolContext(
            context.tenant_id,
            context.run_id,
            "high-1",
            approved=True,
            approval_id=uuid4(),
        )
        with pytest.raises(ToolPolicyError):
            await registry.execute("dangerous", {"value": 1}, approved)

        class ApprovedRequest(ApprovalVerifierPort):
            async def is_approved(
                self, _tenant_id: UUID, _run_id: UUID, _approval_id: UUID, _tool_name: str
            ) -> bool:
                return True

        approved_registry = ToolRegistry(
            InMemoryIdempotencyStore(),
            BudgetEnforcer(BudgetLimits()),
            approval_verifier=ApprovedRequest(),
        )
        approved_registry.register(
            ToolSpec("dangerous", Input, RiskLevel.WRITE_HIGH, write_handler)
        )
        assert await approved_registry.execute("dangerous", {"value": 1}, approved) == {
            "written": True
        }

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
