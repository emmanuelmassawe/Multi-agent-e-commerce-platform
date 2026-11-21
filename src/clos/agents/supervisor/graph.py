"""Resumable LangGraph supervisor with tenant/run-scoped checkpoints."""

import asyncio
import operator
import time
from pathlib import Path
from typing import Annotated, Any, Literal, NotRequired, TypedDict
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from clos.agents.budgets import BudgetLimits
from clos.agents.common import AgentContext, AgentRunner
from clos.application.llm import LLMPort, LLMRequest
from clos.application.delivery import emit

AGENTS = frozenset({"inventory", "pricing", "logistics", "support"})


class AgentResult(TypedDict):
    agent: str
    summary: str


class UsageRecord(TypedDict):
    tenant_id: str
    run_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None


class SupervisorState(TypedDict):
    tenant_id: str
    run_id: str
    message: str
    customer_id: NotRequired[str]
    intent: NotRequired[str]
    agents: NotRequired[list[str]]
    agent_results: Annotated[list[AgentResult], operator.add]
    response: NotRequired[str]
    status: NotRequired[str]
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    tool_calls: NotRequired[int]
    started_at: NotRequired[float]
    usage_records: Annotated[list[UsageRecord], operator.add]


class DispatchState(TypedDict):
    tenant_id: str
    run_id: str
    message: str
    customer_id: NotRequired[str]
    intent: str
    agents: list[str]
    agent: str
    agent_results: list[AgentResult]
    steps: int
    tokens: int
    usage_records: list[UsageRecord]


def tenant_thread_id(tenant_id: UUID, run_id: UUID) -> str:
    """Derive a checkpoint key; callers never supply an unscoped thread ID."""
    return f"{tenant_id}:{run_id}"


def checkpoint_config(tenant_id: UUID, run_id: UUID) -> dict[str, dict[str, str]]:
    """Build the only supported LangGraph checkpoint lookup configuration."""
    return {"configurable": {"thread_id": tenant_thread_id(tenant_id, run_id)}}


def load_prompt(name: str) -> str:
    if name not in {"classify_v1.md", "aggregate_v1.md"}:
        raise ValueError("Unknown versioned prompt")
    prompt_path = Path.cwd() / "prompts" / "supervisor" / name
    return prompt_path.read_text(encoding="utf-8")


def build_supervisor_graph(
    llm: LLMPort,
    *,
    limits: BudgetLimits | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    interrupt_after: list[str] | None = None,
    agent_runners: dict[str, AgentRunner] | None = None,
) -> Any:
    """Create a supervisor graph; independently routed agents fan out in parallel."""
    budget = limits or BudgetLimits()
    builder = StateGraph(SupervisorState)

    async def classify(state: SupervisorState) -> dict[str, object]:
        await emit("node_started",node="classify")
        started_at = state.get("started_at", time.time())
        elapsed = time.time() - started_at
        if elapsed >= budget.max_wall_seconds:
            return {
                "status": "budget_exceeded",
                "response": "Run stopped: wall-clock budget exceeded.",
                "started_at": started_at,
                "steps": 1,
            }
        prompt = f"{load_prompt('classify_v1.md')}\n\nUser request:\n{state['message']}"
        input_estimate = max(1, len(prompt.split()))
        output_limit = budget.max_tokens - input_estimate
        if output_limit < 1:
            return _budget_stop("token", started_at)
        try:
            response = await asyncio.wait_for(
                llm.complete(
                    LLMRequest(
                        task="classify",
                        prompt=prompt,
                        tenant_id=state["tenant_id"],
                        run_id=state["run_id"],
                        max_output_tokens=output_limit,
                    )
                ),
                timeout=max(0.001, budget.max_wall_seconds - elapsed),
            )
        except TimeoutError:
            return _budget_stop("wall-clock", started_at)
        await emit("token_usage",node="classify",model=response.model,input_tokens=response.input_tokens,output_tokens=response.output_tokens)
        routes = [route.strip() for route in response.text.split(",") if route.strip()]
        selected = list(dict.fromkeys(route for route in routes if route in AGENTS))
        if not selected:
            selected = ["support"]
        used_steps = state.get("steps", 0) + 1
        used_tokens = state.get("tokens", 0) + response.input_tokens + response.output_tokens
        usage_record = _usage_record(
            state, response.model, response.input_tokens, response.output_tokens, response.cost_usd
        )
        if used_tokens > budget.max_tokens:
            stopped = _budget_stop("token", started_at)
            stopped.update(
                tokens=response.input_tokens + response.output_tokens,
                usage_records=[usage_record],
            )
            return stopped
        if used_steps + len(selected) + 1 > budget.max_steps:
            stopped = _budget_stop("step", started_at)
            stopped.update(
                tokens=response.input_tokens + response.output_tokens,
                usage_records=[usage_record],
            )
            return stopped
        return {
            "intent": state["message"],
            "agents": selected,
            "started_at": started_at,
            "steps": 1,
            "tokens": response.input_tokens + response.output_tokens,
            "usage_records": [usage_record],
            "status": "running",
        }

    def route(state: SupervisorState) -> str | list[Send]:
        if state.get("status") == "budget_exceeded":
            return "stop"
        return [
            Send(
                "dispatch",
                {
                    "tenant_id": state["tenant_id"],
                    "run_id": state["run_id"],
                    "message": state["message"],
                    **({"customer_id": state["customer_id"]} if state.get("customer_id") else {}),
                    "intent": state["intent"],
                    "agents": state["agents"],
                    "agent": agent,
                    "agent_results": [],
                    "steps": 0,
                    "tokens": 0,
                    "usage_records": [],
                },
            )
            for agent in state["agents"]
        ]

    async def dispatch(state: DispatchState) -> dict[str, object]:
        await emit("node_started",node="dispatch",agent=state["agent"])
        agent = state["agent"]
        runner = (agent_runners or {}).get(agent)
        if runner is not None:
            summary = await runner.run(
                state["message"],
                AgentContext(
                    tenant_id=UUID(state["tenant_id"]),
                    run_id=UUID(state["run_id"]),
                    customer_id=UUID(state["customer_id"]) if state.get("customer_id") else None,
                ),
            )
        else:
            summary = f"Request routed to {agent} agent; no integration runner was configured."
        return {
            "agent_results": [{"agent": agent, "summary": summary}],
            "steps": 1,
        }

    async def aggregate(state: SupervisorState) -> dict[str, object]:
        await emit("node_started",node="aggregate")
        started_at = state.get("started_at", time.monotonic())
        elapsed = time.time() - started_at
        remaining = budget.max_tokens - state.get("tokens", 0)
        if elapsed >= budget.max_wall_seconds:
            return _budget_stop("wall-clock", started_at)
        prompt = (
            f"{load_prompt('aggregate_v1.md')}\n\n"
            f"User request:\n{state['message']}\n\n"
            f"Agent results:\n{state.get('agent_results', [])}"
        )
        input_estimate = max(1, len(prompt.split()))
        output_limit = remaining - input_estimate
        if output_limit < 1:
            return _budget_stop("token", started_at)
        try:
            response = await asyncio.wait_for(
                llm.complete(
                    LLMRequest(
                        task="respond",
                        prompt=prompt,
                        tenant_id=state["tenant_id"],
                        run_id=state["run_id"],
                        max_output_tokens=output_limit,
                    )
                ),
                timeout=max(0.001, budget.max_wall_seconds - elapsed),
            )
        except TimeoutError:
            return _budget_stop("wall-clock", started_at)
        await emit("token_usage",node="aggregate",model=response.model,input_tokens=response.input_tokens,output_tokens=response.output_tokens)
        actual_tokens = response.input_tokens + response.output_tokens
        if actual_tokens > remaining:
            stopped = _budget_stop("token", started_at)
            stopped.update(
                tokens=actual_tokens,
                usage_records=[
                    _usage_record(
                        state,
                        response.model,
                        response.input_tokens,
                        response.output_tokens,
                        response.cost_usd,
                    )
                ],
            )
            return stopped
        if elapsed >= budget.max_wall_seconds:
            return _budget_stop("wall-clock", started_at)
        return {
            "response": response.text,
            "status": "completed",
            "steps": 1,
            "tokens": actual_tokens,
            "usage_records": [
                _usage_record(
                    state,
                    response.model,
                    response.input_tokens,
                    response.output_tokens,
                    response.cost_usd,
                )
            ],
        }

    def stop(state: SupervisorState) -> dict[str, object]:
        return {"response": state.get("response", "Run stopped by a budget limit.")}

    builder.add_node("classify", classify)
    builder.add_node("dispatch", dispatch)
    builder.add_node("aggregate", aggregate)
    builder.add_node("stop", stop)
    builder.add_edge(START, "classify")
    builder.add_conditional_edges("classify", route, {"stop": "stop"})
    builder.add_edge("dispatch", "aggregate")
    builder.add_edge("aggregate", END)
    builder.add_edge("stop", END)
    return builder.compile(checkpointer=checkpointer, interrupt_after=interrupt_after)


def _budget_stop(
    reason: Literal["token", "step", "wall-clock"], started_at: float
) -> dict[str, object]:
    return {
        "status": "budget_exceeded",
        "response": f"Run stopped: {reason} budget exceeded.",
        "started_at": started_at,
        "steps": 1,
    }


def _usage_record(
    state: SupervisorState,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float | None,
) -> UsageRecord:
    return {
        "tenant_id": state["tenant_id"],
        "run_id": state["run_id"],
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
    }
