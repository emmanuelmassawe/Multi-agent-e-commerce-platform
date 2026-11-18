"""Validated typed tools with policy gates, idempotency, timeout, and retries."""

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ValidationError

from clos.agents.budgets import BudgetEnforcer
from clos.domain.identity import AutonomyMode, RiskLevel, may_execute_write


class ToolError(RuntimeError):
    """Base tool execution error."""


class ToolInputError(ToolError):
    """Tool input did not match its declared Pydantic schema."""


class ToolPolicyError(ToolError):
    """Autonomy, approval, or kill-switch policy rejected a tool call."""


class IdempotencyPort(Protocol):
    async def get(self, key: str) -> object | None: ...

    async def put(self, key: str, result: object) -> None: ...


class InMemoryIdempotencyStore:
    """Test fake only; production callers must inject a durable store."""

    def __init__(self) -> None:
        self._results: dict[str, object] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> object | None:
        async with self._lock:
            return self._results.get(key)

    async def put(self, key: str, result: object) -> None:
        async with self._lock:
            self._results.setdefault(key, result)


@dataclass(frozen=True, slots=True)
class ToolContext:
    tenant_id: UUID
    run_id: UUID
    idempotency_key: str
    autonomy_mode: AutonomyMode = AutonomyMode.SHADOW
    in_rule: bool = False
    approved: bool = False
    approval_id: UUID | None = None
    kill_switch_active: bool = False


ToolHandler = Callable[[BaseModel, ToolContext], Awaitable[object]]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    input_model: type[BaseModel]
    risk_level: RiskLevel
    handler: ToolHandler
    timeout_seconds: float = 10.0
    max_retries: int = 2

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Tool name must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("Tool timeout must be positive")
        if self.max_retries < 0:
            raise ValueError("Tool retries cannot be negative")


class ToolRegistry:
    def __init__(
        self,
        idempotency: IdempotencyPort,
        budget: BudgetEnforcer,
        *,
        retry_base_seconds: float = 0.05,
        jitter: Callable[[float, float], float] = random.uniform,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._idempotency = idempotency
        self._budget = budget
        self._tools: dict[str, ToolSpec] = {}
        self._retry_base_seconds = retry_base_seconds
        self._jitter = jitter
        self._sleep = sleep

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    async def execute(
        self,
        name: str,
        raw_input: object,
        context: ToolContext,
    ) -> object:
        try:
            spec = self._tools[name]
        except KeyError as exc:
            raise ToolError(f"Unknown tool: {name}") from exc
        try:
            parsed = spec.input_model.model_validate(raw_input)
        except ValidationError as exc:
            raise ToolInputError("Tool input failed schema validation") from exc
        self._enforce_policy(spec, context)
        scoped_key = f"{context.tenant_id}:{context.run_id}:{name}:{context.idempotency_key}"
        cached = await self._idempotency.get(scoped_key)
        if cached is not None:
            return cached

        self._budget.record_tool_call()
        for attempt in range(spec.max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    spec.handler(parsed, context), timeout=spec.timeout_seconds
                )
                await self._idempotency.put(scoped_key, result)
                return result
            except Exception:
                if attempt == spec.max_retries:
                    raise
                ceiling = self._retry_base_seconds * (2**attempt)
                await self._sleep(max(0.0, self._jitter(0.0, ceiling)))
        raise AssertionError("Retry loop exited unexpectedly")

    @staticmethod
    def _enforce_policy(spec: ToolSpec, context: ToolContext) -> None:
        if spec.risk_level == RiskLevel.READ:
            return
        if context.kill_switch_active:
            raise ToolPolicyError("Writes are blocked while the kill switch is active")
        if spec.risk_level == RiskLevel.WRITE_HIGH:
            if not context.approved or context.approval_id is None:
                raise ToolPolicyError("High-risk tools require an approved request")
            return
        if not may_execute_write(context.autonomy_mode, spec.risk_level, context.in_rule):
            raise ToolPolicyError("Autonomy policy does not permit this write")
