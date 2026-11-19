# Benchmark results

## Phase 2 synthetic supervisor run

Measured on 2026-11-18 with `FakeLLM`; these figures measure local graph overhead only and do not
represent Gemini latency, quality, token billing, or production throughput.

| Run | Dataset | Success rate | p50 | p95 | p99 | Mean synthetic tokens | Tool calls |
|---|---:|---:|---:|---:|---:|---:|---:|
| Supervisor graph | 5 prompts, 500 runs | 100% | 4.43 ms | 11.66 ms | 21.10 ms | 198 | 0 |

Exact environment, source-tree SHA-256, route-level results, tool versions, and command are in
[the raw result](../benchmarks/results/2026-11-18-a563c1fe-phase2-fake.json). Reproduce with:

```powershell
.venv\Scripts\python.exe benchmarks/run_fake_supervisor.py
```

This benchmark used a dirty working tree; the result records the base git SHA and a source-tree
SHA-256 so the measured code snapshot remains identifiable. It is a serial, in-process run without
PostgreSQL checkpoint I/O or RabbitMQ delivery. Real Gemini latency and cost, concurrency, and
queue throughput are **not measured yet**.

## Phase 3 synthetic agent operations

This benchmark runs 100 serial iterations for each fake-backed agent operation on a one-item
synthetic dataset. It measures in-process logic and fake adapter overhead only; it excludes database,
queue, network integration, and LLM latency. Results are in
[the raw Phase 3 result](../benchmarks/results/2026-11-18-08fc6552-phase3-fake.json), including the
source-tree hash and environment. Reproduce with:

```powershell
uv run python benchmarks/run_fake_agents.py
```

These synthetic microsecond-scale timings are not production performance targets. Real integrations,
concurrency, and business outcome rates are **not measured yet**.

## Phase 4 approvals

Approval decision latency, dashboard event delivery latency, and interrupt-to-resume latency are
**not measured yet**. PostgreSQL integration tests validate correctness and checkpoint recovery but
do not report performance numbers.
