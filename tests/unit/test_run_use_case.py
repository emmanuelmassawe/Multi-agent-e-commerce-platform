"""Application orchestration is tenant-scoped and persists usage summaries."""

import asyncio
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from langgraph.types import Command

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


def test_interrupted_run_is_persisted_as_awaiting_approval_and_resumes_with_command() -> None:
    async def scenario() -> None:
        tenant_id, run_id = uuid4(), uuid4()
        payload: dict[str, object] = {"approval_id": str(uuid4()), "decision": "approved"}

        class InterruptGraph:
            def __init__(self) -> None:
                self.inputs: list[object] = []

            async def ainvoke(
                self, state: object, config: dict[str, dict[str, str]]
            ) -> dict[str, Any]:
                self.inputs.append(state)
                assert config["configurable"]["thread_id"] == f"{tenant_id}:{run_id}"
                if isinstance(state, Command):
                    return {
                        "status": "completed",
                        "response": "approved action complete",
                        "usage_records": [],
                    }
                return {
                    "status": "running",
                    "__interrupt__": [
                        SimpleNamespace(value={"approval_id": payload["approval_id"]})
                    ],
                    "usage_records": [],
                }

        graph, repository = InterruptGraph(), RepositoryFake()
        pending = await execute_supervisor_run(
            graph, repository, tenant_id=tenant_id, run_id=run_id, message="change price"
        )
        assert pending["pending_approval"]["approval_id"] == payload["approval_id"]
        assert repository.finished is not None
        assert repository.finished["status"] == "awaiting_approval"

        resumed = await execute_supervisor_run(
            graph,
            repository,
            tenant_id=tenant_id,
            run_id=run_id,
            message="",
            resume=payload,
        )
        assert resumed["status"] == "completed"
        assert isinstance(graph.inputs[-1], Command)
        assert graph.inputs[-1].resume == payload
        assert repository.finished["status"] == "completed"

    asyncio.run(scenario())
