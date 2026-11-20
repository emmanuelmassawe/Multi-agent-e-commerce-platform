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

## Phase 5 customer-scoped retrieval

One local Qdrant 1.12.4 instance ranked synthetic SKU policies from two tenants. Each mode ran 32 serial queries per size. Each query had one known relevant passage. Times include the HTTP request, local feature extraction and filtering, and exclude PostgreSQL hydration and answer generation.

| Points | Eligible | Dense p95 (ms) | Hybrid p95 (ms) | Dense / hybrid recall@5 |
| ---: | ---: | ---: | ---: | ---: |
| 128 | 64 | 99.68 | 91.79 | 1.00 / 1.00 |
| 1,024 | 512 | 139.16 | 79.23 | 1.00 / 1.00 |

[Raw results, exact command, code digests and environment](../benchmarks/results/2026-11-19-0927d4fc-retrieval.json). Merchant-language semantic relevance and concurrent production latency remain unmeasured.

CI reruns the 128-point fixture and fails if hybrid recall@5 drops below 0.95. This is a regression guard for seeded SKU lookups. A latency gate needs repeated measurements on a stable runner.

The [November 20 rerun](../benchmarks/results/2026-11-20-d6d95d82-retrieval.json) used a positive sparse score threshold and a stable ordering for equal scores. Hybrid recall@5 was 1.00 for both sizes. Hybrid p95 was 57.16 ms at 128 points and 73.14 ms at 1,024 points. Each mode ran 32 queries per size.
