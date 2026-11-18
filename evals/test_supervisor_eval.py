"""Deterministic golden checks for the Phase 2 supervisor routing contract."""

from uuid import uuid4

import pytest

from clos.agents.llm import FakeLLM
from clos.agents.supervisor.graph import build_supervisor_graph


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Check stock and price", {"inventory", "pricing"}),
        ("Where is my shipment?", {"logistics"}),
        ("I need customer support", {"support"}),
    ],
)
def test_golden_supervisor_routes(message: str, expected: set[str]) -> None:
    async def scenario() -> None:
        tenant_id, run_id = uuid4(), uuid4()
        graph = build_supervisor_graph(FakeLLM())
        result = await graph.ainvoke(
            {
                "tenant_id": str(tenant_id),
                "run_id": str(run_id),
                "message": message,
                "agent_results": [],
                "steps": 0,
                "tokens": 0,
                "usage_records": [],
            }
        )
        assert set(result["agents"]) == expected
        assert result["status"] == "completed"
        assert result["usage_records"]

    import asyncio

    asyncio.run(scenario())
