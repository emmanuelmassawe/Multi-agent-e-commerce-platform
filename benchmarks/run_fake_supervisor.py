"""Reproducible synthetic benchmark for the Phase 2 supervisor graph."""

from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import statistics
import subprocess
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from clos.adapters.llm.providers import FakeLLM
from clos.agents.supervisor.graph import build_supervisor_graph

DATASET = (
    "Check stock at my warehouse",
    "Compare our price with competitors",
    "Track my shipment delivery",
    "Customer support for my order",
    "Check stock and price",
)
REPEATS = 100


class Observation(TypedDict):
    message_case: str
    agents: list[str]
    latency_ms: float
    status: str
    tokens: int
    tool_calls: int


def percentile(values: list[float], percentile_value: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile_value)))
    return ordered[index]


async def measure() -> list[Observation]:
    graph = build_supervisor_graph(FakeLLM())
    measurements: list[Observation] = []
    for message in DATASET:
        for _ in range(REPEATS):
            tenant_id, run_id = uuid4(), uuid4()
            start = time.perf_counter()
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
            measurements.append(
                {
                    "message_case": message,
                    "agents": result.get("agents", []),
                    "latency_ms": (time.perf_counter() - start) * 1_000,
                    "status": result.get("status"),
                    "tokens": result.get("tokens", 0),
                    "tool_calls": result.get("tool_calls", 0),
                }
            )
    return measurements


def main() -> None:
    stamp = datetime.now(UTC)
    git_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--short"], check=True, capture_output=True, text=True
        ).stdout.strip()
    )
    source_hash = hashlib.sha256()
    files = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    for filename in sorted(
        file for file in files if not file.startswith(("benchmarks/results/", "docs/", ".coverage"))
    ):
        source_hash.update(filename.encode("utf-8"))
        source_path = Path(filename)
        source_hash.update(source_path.read_bytes() if source_path.exists() else b"<deleted>")
    measurements = asyncio.run(measure())
    latencies = [float(item["latency_ms"]) for item in measurements]
    completed = sum(item["status"] == "completed" for item in measurements)
    by_route_case: dict[str, dict[str, object]] = {}
    output: dict[str, object] = {
        "date_utc": stamp.isoformat(),
        "git_sha": git_sha,
        "working_tree_dirty": dirty,
        "source_tree_sha256": source_hash.hexdigest(),
        "environment": {
            "os": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "langgraph": version("langgraph"),
            "langgraph_checkpoint_postgres": version("langgraph-checkpoint-postgres"),
            "google_genai": version("google-genai"),
            "llm": "FakeLLM (synthetic; no provider call)",
        },
        "dataset_size": len(DATASET),
        "runs": len(measurements),
        "repeats_per_case": REPEATS,
        "command": ".venv\\Scripts\\python.exe benchmarks/run_fake_supervisor.py",
        "summary": {
            "success_rate": completed / len(measurements),
            "latency_ms_p50": percentile(latencies, 0.50),
            "latency_ms_p95": percentile(latencies, 0.95),
            "latency_ms_p99": percentile(latencies, 0.99),
            "mean_tokens_per_run": statistics.mean(int(item["tokens"]) for item in measurements),
            "mean_tool_calls_per_run": statistics.mean(
                int(item["tool_calls"]) for item in measurements
            ),
        },
        "by_route_case": by_route_case,
        "observations": measurements,
    }
    for message in DATASET:
        selected = [item for item in measurements if item["message_case"] == message]
        route_latencies = [float(item["latency_ms"]) for item in selected]
        by_route_case[message] = {
            "agents": selected[0]["agents"],
            "runs": len(selected),
            "success_rate": sum(item["status"] == "completed" for item in selected) / len(selected),
            "latency_ms_p50": percentile(route_latencies, 0.50),
            "latency_ms_p95": percentile(route_latencies, 0.95),
            "mean_tool_calls": statistics.mean(int(item["tool_calls"]) for item in selected),
        }
    results = Path("benchmarks/results")
    results.mkdir(parents=True, exist_ok=True)
    path = results / f"{stamp:%Y-%m-%d}-{git_sha[:8]}-phase2-fake.json"
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
