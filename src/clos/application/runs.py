"""Use case for tenant-scoped, resumable supervisor runs."""

from typing import Any, Protocol
from uuid import UUID

from clos.agents.supervisor.graph import UsageRecord, checkpoint_config


class RunRepositoryPort(Protocol):
    async def start(self, tenant_id: UUID, run_id: UUID) -> None: ...

    async def finish(
        self,
        tenant_id: UUID,
        run_id: UUID,
        *,
        status: str,
        explanation: dict[str, Any],
        usage_records: list[UsageRecord],
    ) -> None: ...


class CompiledGraphPort(Protocol):
    async def ainvoke(
        self, state: dict[str, object], config: dict[str, dict[str, str]]
    ) -> dict[str, Any]: ...


async def execute_supervisor_run(
    graph: CompiledGraphPort,
    repository: RunRepositoryPort,
    *,
    tenant_id: UUID,
    run_id: UUID,
    message: str,
) -> dict[str, Any]:
    """Start or resume a graph and persist final status plus token usage."""
    await repository.start(tenant_id, run_id)
    initial_state: dict[str, object] = {
        "tenant_id": str(tenant_id),
        "run_id": str(run_id),
        "message": message,
        "agent_results": [],
        "steps": 0,
        "tokens": 0,
        "usage_records": [],
    }
    result = await graph.ainvoke(initial_state, checkpoint_config(tenant_id, run_id))
    await repository.finish(
        tenant_id,
        run_id,
        status=str(result.get("status", "failed")),
        explanation={
            "intent": result.get("intent"),
            "agents": result.get("agents", []),
            "response": result.get("response", ""),
            "budget": {
                "tokens": result.get("tokens", 0),
                "steps": result.get("steps", 0),
                "tool_calls": result.get("tool_calls", 0),
            },
        },
        usage_records=result.get("usage_records", []),
    )
    return result
