"""Application orchestration is tenant-scoped and persists usage summaries."""

import asyncio
from typing import Any
from uuid import UUID, uuid4

from clos.agents.supervisor.graph import UsageRecord
from clos.application.runs import execute_supervisor_run


class GraphFake:
    async def ainvoke(
        self, state: dict[str, object], config: dict[str, dict[str, str]]
    ) -> dict[str, Any]:
        assert config["configurable"]["thread_id"] == (f"{state['tenant_id']}:{state['run_id']}")
        return {
            "intent": "check stock",
            "agents": ["inventory"],
            "response": "Routed",
            "status": "completed",
            "tokens": 7,
            "steps": 4,
            "tool_calls": 0,
            "usage_records": [
                {
                    "tenant_id": str(state["tenant_id"]),
                    "run_id": str(state["run_id"]),
                    "model": "fake-deterministic",
                    "input_tokens": 4,
                    "output_tokens": 3,
                    "cost_usd": 0,
                }
            ],
        }


class RepositoryFake:
    def __init__(self) -> None:
        self.started: tuple[UUID, UUID] | None = None
        self.finished: dict[str, Any] | None = None

    async def start(self, tenant_id: UUID, run_id: UUID) -> None:
        self.started = (tenant_id, run_id)

    async def finish(
        self,
        tenant_id: UUID,
        run_id: UUID,
        *,
        status: str,
        explanation: dict[str, Any],
        usage_records: list[UsageRecord],
    ) -> None:
        assert self.started == (tenant_id, run_id)
        self.finished = {
            "status": status,
            "explanation": explanation,
            "usage_records": usage_records,
        }


def test_supervisor_run_uses_tenant_scoped_checkpoint_and_persists_tokens() -> None:
    async def scenario() -> None:
        tenant_id, run_id = uuid4(), uuid4()
        repository = RepositoryFake()
        result = await execute_supervisor_run(
            GraphFake(),
            repository,
            tenant_id=tenant_id,
            run_id=run_id,
            message="check stock",
        )
        assert result["status"] == "completed"
        assert repository.finished is not None
        assert repository.finished["status"] == "completed"
        assert repository.finished["usage_records"][0]["input_tokens"] == 4
        assert repository.finished["explanation"]["budget"]["steps"] == 4

    asyncio.run(scenario())
