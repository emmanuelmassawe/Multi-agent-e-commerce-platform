"""Measure POST /v1/runs against a local Uvicorn process and a dedicated test database."""

import argparse
import asyncio
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from sqlalchemy import delete, text

from clos.adapters.db.models import Tenant, User
from clos.adapters.db.session import make_session_factory, tenant_session
from clos.adapters.security.crypto import JwtTokenIssuer
from clos.domain.identity import Role

LOCUST = "2.42.1"


async def fixture(url: str, tenant: UUID, actor: UUID, *, cleanup: bool) -> str:
    sessions = make_session_factory(url)
    try:
        async with tenant_session(sessions, tenant) as db:
            if cleanup:
                await db.execute(delete(Tenant).where(Tenant.id == tenant))
                return ""
            db.add(Tenant(id=tenant, name="Synthetic benchmark", slug=tenant.hex))
            await db.flush()
            db.add(
                User(
                    id=actor,
                    tenant_id=tenant,
                    email="bench@example.invalid",
                    full_name="Synthetic merchant",
                    role="owner",
                    password_hash="unused",
                )
            )
            return str(await db.scalar(text("SHOW server_version")))
    finally:
        await sessions.kw["bind"].dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=4)
    parser.add_argument("--seconds", type=int, default=15)
    args = parser.parse_args()
    if args.users < 1 or args.seconds < 2:
        parser.error("Expected positive users and at least two seconds")
    url = os.environ["TEST_DATABASE_URL"]
    tenant, actor = uuid4(), uuid4()
    secret = secrets.token_hex(32)
    token = JwtTokenIssuer(secret).create_access_token(
        user_id=actor, tenant_id=tenant, role=Role.OWNER, expires_in_seconds=args.seconds + 300
    )
    env = {
        **os.environ,
        "DATABASE_URL": url,
        "APP_ENV": "test",
        "AUTH_JWT_SECRET": secret,
        "INTEGRATIONS": "{}",
        "TENANT_REQUESTS_PER_MINUTE": "1000000",
        "USER_REQUESTS_PER_MINUTE": "1000000",
    }
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    host = f"http://127.0.0.1:{port}"
    postgres = asyncio.run(fixture(url, tenant, actor, cleanup=False))
    try:
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / "load"
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "clos.apps.api.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "warning",
                    "--no-access-log",
                ],
                env=env,
            )
            try:
                with httpx.Client(base_url=host, trust_env=False, timeout=2) as client:
                    deadline = time.monotonic() + 60
                    while server.poll() is None and time.monotonic() < deadline:
                        try:
                            if client.get("/health/ready").status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        time.sleep(0.2)
                    else:
                        raise RuntimeError("Benchmark API did not become ready")
                load = subprocess.run(
                    [
                        "uvx",
                        "--from",
                        f"locust=={LOCUST}",
                        "locust",
                        "-f",
                        "benchmarks/locustfile.py",
                        "--headless",
                        "--host",
                        host,
                        "-u",
                        str(args.users),
                        "-r",
                        str(args.users),
                        "-t",
                        f"{args.seconds}s",
                        "--only-summary",
                        "--csv",
                        str(prefix),
                    ],
                    env={**os.environ, "CLOS_BENCH_TOKEN": token},
                    timeout=args.seconds + 180,
                )
                with prefix.with_name("load_stats.csv").open(newline="", encoding="utf8") as stats:
                    rows = list(csv.DictReader(stats))
            finally:
                server.terminate()
                server.wait(timeout=30)
        total = next(row for row in rows if row["Name"] == "Aggregated")
        count, failures = int(total["Request Count"]), int(total["Failure Count"])
        now = datetime.now(UTC)
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        sources = sorted(
            [
                *Path("src/clos").rglob("*.py"),
                Path("benchmarks/locustfile.py"),
                Path(__file__),
                Path("uv.lock"),
            ],
            key=lambda p: p.resolve().relative_to(Path.cwd()).as_posix(),
        )
        digest = hashlib.sha256()
        for path in sources:
            digest.update(
                path.relative_to(Path.cwd()).as_posix().encode()
                if path.is_absolute()
                else path.as_posix().encode()
            )
            digest.update(path.read_bytes())
        result = {
            "timestamp": now.isoformat(),
            "git_sha": sha,
            "source_sha256": digest.hexdigest(),
            "environment": platform.platform(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "python": platform.python_version(),
            "postgres": postgres,
            "locust": LOCUST,
            "uvicorn": importlib.metadata.version("uvicorn"),
            "command": (
                "uv run --locked python benchmarks/run_api_load.py "
                f"--users {args.users} --seconds {args.seconds}"
            ),
            "dataset": {
                "tenants": 1,
                "users": 1,
                "virtual_users": args.users,
                "seconds": args.seconds,
                "unique_run_requests": count,
            },
            "scope": "Authenticated run admission with PostgreSQL and Redis. Worker excluded.",
            "rps": float(total["Requests/s"]),
            "p50_ms": float(total["50%"]),
            "p95_ms": float(total["95%"]),
            "p99_ms": float(total["99%"]),
            "requests": count,
            "failures": failures,
            "error_rate": failures / count if count else None,
            "locust_stats": rows,
        }
        target = Path("benchmarks/results") / f"{now:%Y-%m-%dT%H%M%SZ}-{sha[:8]}-api.json"
        target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
        print(target)
        if load.returncode or not count or failures:
            raise SystemExit(
                "Load gate failed: benchmark requires accepted requests and zero errors"
            )
    finally:
        asyncio.run(fixture(url, tenant, actor, cleanup=True))


if __name__ == "__main__":
    main()
