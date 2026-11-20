"""Measure real HTTP searches against a temporary, synthetic Qdrant collection."""

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import TypedDict
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx

from clos.adapters.qdrant import QdrantVectorStore
from clos.application.memory import Point


class RetrievalResult(TypedDict):
    points: int
    eligible_points: int
    queries_per_mode: int
    qdrant: str
    modes: dict[str, dict[str, float]]


async def measure(size: int, queries: int, url: str) -> RetrievalResult:
    tenant, foreign, customer = (uuid5(NAMESPACE_URL, "clos-bench:" + x) for x in ("A", "B", "C"))
    name = "clos_benchmark_" + uuid4().hex
    points = []
    for i in range(size):
        scope = foreign if i % 2 else tenant
        uid = uuid5(scope, str(i))
        topic = ["returns", "delivery", "pricing"][i % 3]
        points.append(
            Point(uid, scope, customer, f"Product SKU{i // 2:06d} {topic} merchant policy")
        )
    async with httpx.AsyncClient(base_url=url, timeout=30) as client:
        store = QdrantVectorStore(client, name)
        server = (await client.get("/")).raise_for_status().json()["version"]
        await store.ensure()
        try:
            await store.upsert(points)
            modes = {}
            indices = [2 * (i * (size // 2) // queries) for i in range(queries)]
            for hybrid in (False, True):
                elapsed = []
                matches = 0
                for index in indices:
                    start = perf_counter()
                    ids = await store.query(
                        tenant, customer, f"policy SKU{index // 2:06d}", 5, hybrid=hybrid
                    )
                    elapsed.append(1000 * (perf_counter() - start))
                    matches += points[index].id in ids
                modes["hybrid" if hybrid else "dense"] = {
                    "p95_ms": sorted(elapsed)[math.ceil(0.95 * queries) - 1],
                    "recall_at_5": matches / queries,
                }
            return {
                "points": size,
                "eligible_points": size // 2,
                "queries_per_mode": queries,
                "qdrant": server,
                "modes": modes,
            }
        finally:
            (await client.delete(store.path)).raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", nargs="+", type=int, default=[128, 1024])
    parser.add_argument("--queries", type=int, default=32)
    parser.add_argument("--min-hybrid-recall", type=float, default=0.0)
    args = parser.parse_args()
    if args.queries < 1 or any(s % 2 or s // 2 < args.queries for s in args.sizes):
        parser.error("Each size must be even and allow one distinct query per eligible point")
    stamp = datetime.now(UTC)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    files = [
        Path(__file__),
        Path("src/clos/adapters/qdrant.py"),
        Path("src/clos/application/memory.py"),
    ]
    results = [
        asyncio.run(measure(s, args.queries, os.getenv("QDRANT_URL", "http://localhost:6333")))
        for s in args.sizes
    ]
    report = {
        "date": stamp.isoformat(),
        "git_sha": sha,
        "source_sha256": {str(p.name): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "environment": platform.platform(),
        "cpu": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "httpx": version("httpx"),
        "command": "uv run python benchmarks/run_retrieval.py " + " ".join(sys.argv[1:]),
        "dataset": "Synthetic SKU lookup. One relevant passage per query, two tenants.",
        "results": results,
    }
    path = Path("benchmarks/results") / f"{stamp:%Y-%m-%d}-{sha[:8]}-retrieval.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    print(path)
    print(json.dumps(results))
    if any(row["modes"]["hybrid"]["recall_at_5"] < args.min_hybrid_recall for row in results):
        raise SystemExit("Hybrid recall@5 below the configured synthetic regression threshold")


if __name__ == "__main__":
    main()
