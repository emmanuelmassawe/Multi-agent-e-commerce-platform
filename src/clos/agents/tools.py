"""Validated typed tools with policy gates, idempotency, timeout, and retries."""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Protocol
from uuid import UUID

from langgraph.types import interrupt
from pydantic import BaseModel, ValidationError

from clos.agents.budgets import BudgetEnforcer
from clos.application.delivery import emit
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
        self,
        tenant_id: UUID,
        run_id: UUID,
        approval_id: UUID,
        tool_name: str,
        tool_input: dict[str, object],
    ) -> bool: ...


class ApprovalRequesterPort(Protocol):
    async def request_tool_approval(
        self,
        tenant_id: UUID,
        run_id: UUID,
        tool_name: str,
        tool_input: dict[str, object],
        *,
        context: dict[str, object] | None = None,
        idempotency_key: str,
    ) -> object: ...


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
    approval_context: dict[str, object] | None = None


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
        approval_requester: ApprovalRequesterPort | None = None,
        interrupt_fn: Callable[[dict[str, object]], object] = interrupt,
    ) -> None:
        self._idempotency = idempotency
        self._budget = budget
        self._tools: dict[str, ToolSpec] = {}
        self._retry_base_seconds = retry_base_seconds
        self._jitter = jitter
        self._sleep = sleep
        self._approval_verifier = approval_verifier
        self._approval_requester = approval_requester
        self._interrupt = interrupt_fn
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
        execution_context = context
        rejected_approval_id: UUID | None = None
        if spec.risk_level == RiskLevel.WRITE_HIGH:
            parsed, execution_context, rejected_approval_id = await self._approval_gate(
                name, spec.input_model, parsed, context
            )
        if spec.risk_level != RiskLevel.WRITE_HIGH:
            await self._enforce_policy(spec, execution_context)
        scoped_key = f"{context.tenant_id}:{context.run_id}:{name}:{context.idempotency_key}"

        async def run_with_retries() -> object:
            self._budget.record_tool_call()
            for attempt in range(spec.max_retries + 1):
                elapsed = time.monotonic() - self._started_at
                self._budget.check_time(elapsed)
                remaining = self._budget.limits.max_wall_seconds - elapsed
                try:
                    if rejected_approval_id is not None:
                        return {"status": "rejected", "approval_id": str(rejected_approval_id)}
                    await emit("tool_started", tool=name, attempt=attempt + 1)
                    result = await asyncio.wait_for(
                        spec.handler(parsed, execution_context),
                        timeout=min(spec.timeout_seconds, remaining),
                    )
                except Exception:
                    await emit("tool_finished", tool=name, attempt=attempt + 1, outcome="error")
                    if attempt == spec.max_retries:
                        raise
                    ceiling = self._retry_base_seconds * (2**attempt)
                    await self._sleep(max(0.0, self._jitter(0.0, ceiling)))
                else:
                    await emit("tool_finished", tool=name, attempt=attempt + 1, outcome="success")
                    return result
            raise AssertionError("Retry loop exited unexpectedly")

        return await self._idempotency.run_once(
            scoped_key,
            run_with_retries,
            risk_level=spec.risk_level,
            input_data=parsed.model_dump(mode="json"),
        )

    async def _approval_gate(
        self,
        tool_name: str,
        input_model: type[BaseModel],
        parsed: BaseModel,
        context: ToolContext,
    ) -> tuple[BaseModel, ToolContext, UUID | None]:
        input_data = parsed.model_dump(mode="json")
        if context.kill_switch_active:
            raise ToolPolicyError("Writes are blocked while the kill switch is active")
        if context.approved and context.approval_id is not None:
            await self._enforce_policy(
                ToolSpec(tool_name, input_model, RiskLevel.WRITE_HIGH, _unused_handler),
                context,
                input_data,
            )
            return parsed, context, None
        if self._approval_requester is None or self._approval_verifier is None:
            raise ToolPolicyError(
                "High-risk tools require an approved request and an approval workflow"
            )
        item = await self._approval_requester.request_tool_approval(
            context.tenant_id,
            context.run_id,
            tool_name,
            input_data,
            context=context.approval_context,
            idempotency_key=context.idempotency_key,
        )
        approval_id = getattr(item, "approval_id", None)
        if not isinstance(approval_id, UUID):
            raise ToolPolicyError("Approval workflow did not return a valid request ID")
        resumed = self._interrupt(
            {
                "type": "approval_required",
                "approval_id": str(approval_id),
                "tenant_id": str(context.tenant_id),
                "run_id": str(context.run_id),
                "tool_name": tool_name,
                "tool_input": input_data,
            }
        )
        if not isinstance(resumed, dict) or resumed.get("approval_id") != str(approval_id):
            raise ToolPolicyError("Approval resume payload does not match the pending request")
        decision = resumed.get("decision")
        if decision == "rejected":
            return parsed, context, approval_id
        if decision != "approved":
            raise ToolPolicyError("Approval decision is missing or invalid")
        modified_input = resumed.get("tool_input", input_data)
        try:
            parsed = input_model.model_validate(modified_input)
        except ValidationError as exc:
            raise ToolInputError("Approved tool input failed schema validation") from exc
        authorized_context = replace(context, approved=True, approval_id=approval_id)
        await self._enforce_policy(
            ToolSpec(tool_name, input_model, RiskLevel.WRITE_HIGH, _unused_handler),
            authorized_context,
            parsed.model_dump(mode="json"),
        )
        return parsed, authorized_context, None

    async def _enforce_policy(
        self,
        spec: ToolSpec,
        context: ToolContext,
        tool_input: dict[str, object] | None = None,
    ) -> None:
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
                context.tenant_id,
                context.run_id,
                context.approval_id,
                spec.name,
                tool_input or {},
            )
            if not is_approved:
                raise ToolPolicyError("Approval request does not authorize this tool")
            return
        if not may_execute_write(context.autonomy_mode, spec.risk_level, context.in_rule):
            raise ToolPolicyError("Autonomy policy does not permit this write")


async def _unused_handler(_data: BaseModel, _context: ToolContext) -> object:
    raise AssertionError("Policy-only tool spec cannot execute")
