"""Reproducible in-process synthetic benchmark for Phase 3 agent operations."""

from __future__ import annotations

import asyncio
import hashlib
import json
import platform
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from clos.adapters.integrations.fakes import FakeCommerce
from clos.agents.common import (
    AgentContext,
    CompetitorPrice,
    PriceRule,
    RetrievedDocument,
    RouteOption,
    Shipment,
    StockLevel,
)
from clos.agents.inventory import InventoryAgent
from clos.agents.logistics import LogisticsAgent
from clos.agents.pricing import PricingAgent
from clos.agents.support import SupportAgent

REPEATS = 100


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * quantile))]


async def measure() -> dict[str, list[float]]:
    fake = FakeCommerce()
    tenant, product, warehouse, shipment_id, customer_id = (uuid4() for _ in range(5))
    context = AgentContext(tenant, uuid4(), customer_id)
    fake.stock[(tenant, product)] = [StockLevel(product, warehouse, 30, 2, 4.0, 3.0)]
    fake.competitors[(tenant, product)] = [CompetitorPrice("synthetic", 19.0, "USD")]
    fake.shipments[(tenant, shipment_id)] = Shipment(shipment_id, "in_transit")
    fake.documents[(tenant, customer_id)] = [RetrievedDocument(uuid4(), "Synthetic policy", "fake")]
    inventory, pricing = InventoryAgent(fake), PricingAgent(fake)
    logistics, support = LogisticsAgent(fake), SupportAgent(fake)
    timings: dict[str, list[float]] = {
        name: [] for name in ("inventory", "pricing", "logistics", "support")
    }
    for _ in range(REPEATS):
        start = time.perf_counter()
        await inventory.forecast_stockout(product, context)
        timings["inventory"].append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        competitors = await pricing.fetch_competitor_prices(product, context)
        pricing.compute_price_recommendation(
            current_price=20, cost=10, competitors=competitors, rule=PriceRule(min_margin=0.2)
        )
        timings["pricing"].append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        await logistics.track_shipment(shipment_id, context)
        logistics.plan_route([RouteOption("fake", 10, 24)])
        timings["logistics"].append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        await support.answer_customer("synthetic question", context)
        timings["support"].append((time.perf_counter() - start) * 1000)
    return timings


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
    digest = hashlib.sha256()
    tracked = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    for name in sorted(
        file for file in tracked if not file.startswith(("benchmarks/results/", "docs/"))
    ):
        path = Path(name)
        digest.update(name.encode())
        digest.update(path.read_bytes() if path.exists() else b"<deleted>")
    timings = asyncio.run(measure())
    summary = {
        agent: {
            "runs": len(values),
            "success_rate": 1.0,
            "latency_ms_p50": percentile(values, 0.50),
            "latency_ms_p95": percentile(values, 0.95),
            "latency_ms_p99": percentile(values, 0.99),
            "mean_latency_ms": statistics.mean(values),
        }
        for agent, values in timings.items()
    }
    output = {
        "date_utc": stamp.isoformat(),
        "git_sha": git_sha,
        "working_tree_dirty": dirty,
        "source_tree_sha256": digest.hexdigest(),
        "environment": {
            "os": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "llm": "none; deterministic fakes only",
        },
        "dataset_size": 1,
        "runs_per_agent": REPEATS,
        "command": "uv run python benchmarks/run_fake_agents.py",
        "summary": summary,
        "scope": "serial in-process operations; excludes network, database, queue, and LLM latency",
    }
    results = Path("benchmarks/results")
    results.mkdir(exist_ok=True)
    path = results / f"{stamp:%Y-%m-%d}-{git_sha[:8]}-phase3-fake.json"
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
