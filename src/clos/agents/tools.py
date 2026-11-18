"""Validated typed tools with policy gates, idempotency, timeout, and retries."""

import asyncio
import random
import time
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


class ToolIdempotencyConflict(ToolError):
    """The same idempotency key was reused with different validated input."""


class IdempotencyPort(Protocol):
    async def run_once(
        self,
        key: str,
        action: Callable[[], Awaitable[object]],
        *,
        risk_level: RiskLevel,
        input_data: dict[str, object],
    ) -> object: ...


class ApprovalVerifierPort(Protocol):
    async def is_approved(
        self, tenant_id: UUID, run_id: UUID, approval_id: UUID, tool_name: str
    ) -> bool: ...


class InMemoryIdempotencyStore:
    """Test fake only; production callers must inject a durable store."""

    def __init__(self) -> None:
        self._results: dict[str, tuple[dict[str, object], object]] = {}
        self._guard = asyncio.Lock()
        self._locks: dict[str, asyncio.Lock] = {}

    async def run_once(
        self,
        key: str,
        action: Callable[[], Awaitable[object]],
        *,
        risk_level: RiskLevel,
        input_data: dict[str, object],
    ) -> object:
        async with self._guard:
            lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if key in self._results:
                previous_input, previous_result = self._results[key]
                if previous_input != input_data:
                    raise ToolIdempotencyConflict("Idempotency key reused with different input")
                return previous_result
            result = await action()
            self._results[key] = (input_data, result)
            return result


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
        approval_verifier: ApprovalVerifierPort | None = None,
    ) -> None:
        self._idempotency = idempotency
        self._budget = budget
        self._tools: dict[str, ToolSpec] = {}
        self._retry_base_seconds = retry_base_seconds
        self._jitter = jitter
        self._sleep = sleep
        self._approval_verifier = approval_verifier
        self._started_at = time.monotonic()

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
        if not context.idempotency_key.strip():
            raise ValueError("Tool idempotency key must not be empty")
        try:
            spec = self._tools[name]
        except KeyError as exc:
            raise ToolError(f"Unknown tool: {name}") from exc
        try:
            parsed = spec.input_model.model_validate(raw_input)
        except ValidationError as exc:
            raise ToolInputError("Tool input failed schema validation") from exc
        await self._enforce_policy(spec, context)
        scoped_key = f"{context.tenant_id}:{context.run_id}:{name}:{context.idempotency_key}"

        async def run_with_retries() -> object:
            self._budget.record_tool_call()
            for attempt in range(spec.max_retries + 1):
                elapsed = time.monotonic() - self._started_at
                self._budget.check_time(elapsed)
                remaining = self._budget.limits.max_wall_seconds - elapsed
                try:
                    return await asyncio.wait_for(
                        spec.handler(parsed, context),
                        timeout=min(spec.timeout_seconds, remaining),
                    )
                except Exception:
                    if attempt == spec.max_retries:
                        raise
                    ceiling = self._retry_base_seconds * (2**attempt)
                    await self._sleep(max(0.0, self._jitter(0.0, ceiling)))
            raise AssertionError("Retry loop exited unexpectedly")

        return await self._idempotency.run_once(
            scoped_key,
            run_with_retries,
            risk_level=spec.risk_level,
            input_data=parsed.model_dump(mode="json"),
        )

    async def _enforce_policy(self, spec: ToolSpec, context: ToolContext) -> None:
        if spec.risk_level == RiskLevel.READ:
            return
        if context.kill_switch_active:
            raise ToolPolicyError("Writes are blocked while the kill switch is active")
        if spec.risk_level == RiskLevel.WRITE_HIGH:
            if (
                not context.approved
                or context.approval_id is None
                or self._approval_verifier is None
            ):
                raise ToolPolicyError("High-risk tools require an approved request")
            is_approved = await self._approval_verifier.is_approved(
                context.tenant_id, context.run_id, context.approval_id, spec.name
            )
            if not is_approved:
                raise ToolPolicyError("Approval request does not authorize this tool")
            return
        if not may_execute_write(context.autonomy_mode, spec.risk_level, context.in_rule):
            raise ToolPolicyError("Autonomy policy does not permit this write")
