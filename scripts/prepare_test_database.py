"""Create the restricted database role used by PostgreSQL integration tests."""

from __future__ import annotations

import asyncio
import os

import asyncpg  # type: ignore[import-untyped]
from sqlalchemy.engine import make_url


async def main() -> None:
    admin_url = os.environ.get("DATABASE_ADMIN_URL")
    password = os.environ.get("CLOS_APP_PASSWORD")
    if admin_url is None or password is None:
        raise RuntimeError("DATABASE_ADMIN_URL and CLOS_APP_PASSWORD are required")
    url = make_url(admin_url)
    connection = await asyncpg.connect(
        host=url.host,
        port=url.port or 5432,
        database=url.database,
        user=url.username,
        password=url.password,
    )
    try:
        role_exists = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'clos_app')"
        )
        escaped_password = password.replace("'", "''")
        if not role_exists:
            await connection.execute(
                f"CREATE ROLE clos_app LOGIN PASSWORD '{escaped_password}' NOSUPERUSER NOBYPASSRLS"
            )
        await connection.execute(f'GRANT CONNECT ON DATABASE "{url.database}" TO clos_app')
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
