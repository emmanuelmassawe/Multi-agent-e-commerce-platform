"""Create LangGraph's checkpoint schema using the migration/admin database URL."""

from __future__ import annotations

import asyncio
import os
import sys

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.engine import make_url


def psycopg_url(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


async def main() -> None:
    admin_url = os.environ.get("DATABASE_ADMIN_URL")
    if admin_url is None:
        raise RuntimeError("DATABASE_ADMIN_URL is required for checkpoint schema setup")
    async with AsyncPostgresSaver.from_conn_string(psycopg_url(admin_url)) as saver:
        await saver.setup()
        await saver.conn.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON "
            "checkpoint_migrations, checkpoints, checkpoint_blobs, checkpoint_writes "
            "TO clos_app"
        )


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
