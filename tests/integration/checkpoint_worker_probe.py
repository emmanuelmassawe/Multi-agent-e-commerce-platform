"""Helper subprocess that checkpoints a graph and waits to be terminated."""

import asyncio
import json
import os
import selectors
import sys
from pathlib import Path
from uuid import UUID

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.engine import make_url

from clos.adapters.llm.providers import FakeLLM
from clos.agents.supervisor.graph import build_supervisor_graph, checkpoint_config


def _psycopg_url(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


async def main(mode: str, tenant_id: UUID, run_id: UUID, marker: Path) -> None:
    database_url = os.environ["CHECKPOINT_DATABASE_URL"]
    config = checkpoint_config(tenant_id, run_id)
    async with AsyncPostgresSaver.from_conn_string(_psycopg_url(database_url)) as saver:
        if mode == "pause":
            graph = build_supervisor_graph(
                FakeLLM(), checkpointer=saver, interrupt_after=["classify"]
            )
            await graph.ainvoke(
                {
                    "tenant_id": str(tenant_id),
                    "run_id": str(run_id),
                    "message": "Check stock and price",
                    "agent_results": [],
                    "steps": 0,
                    "tokens": 0,
                    "usage_records": [],
                },
                config,
            )
            marker.write_text("checkpoint saved", encoding="utf-8")
            await asyncio.Event().wait()
        elif mode == "resume":
            graph = build_supervisor_graph(FakeLLM(), checkpointer=saver)
            result = await graph.ainvoke(None, config)
            print(json.dumps({"status": result["status"], "agents": result["agents"]}))
        else:
            raise ValueError("Expected pause or resume mode")


if __name__ == "__main__":

    def loop_factory() -> asyncio.AbstractEventLoop:
        if sys.platform == "win32":
            return asyncio.SelectorEventLoop(selectors.SelectSelector())
        return asyncio.new_event_loop()

    async def probe() -> None:
        async with asyncio.timeout(30):
            await main(sys.argv[1], UUID(sys.argv[2]), UUID(sys.argv[3]), Path(sys.argv[4]))

    asyncio.run(probe(), loop_factory=loop_factory)
