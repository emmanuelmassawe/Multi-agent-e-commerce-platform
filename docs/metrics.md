# Metrics and measurement status

All benchmark figures remain **not measured yet** unless produced by a script in `benchmarks/` or
observed from live metrics. Phase 2 uses the deterministic fake LLM in tests; its token and cost
values are synthetic and are not production measurements.

## Phase 2 runtime metrics

| Metric | Labels | Source | Status |
|---|---|---|---|
| `agent_run_duration_seconds` | tenant, agent, outcome | worker runtime | instrumentation pending |
| `agent_run_success_total` | tenant, agent, outcome | worker runtime | instrumentation pending |
| `llm_tokens_total` | tenant, agent, model, direction | persisted `TokenUsage` | available in run records; Prometheus export pending |
| `llm_cost_usd_total` | tenant, agent, model | persisted `TokenUsage` | available when provider returns cost; real provider not configured |
| `budget_exceeded_total` | tenant, budget | supervisor runtime | status recorded on `AgentRun`; Prometheus export pending |
| `tool_call_duration_seconds` | tenant, tool, outcome | tool registry | instrumentation pending |
| `tool_call_errors_total` | tenant, tool, risk_level | `ToolCall` records | persisted tool-call outcomes; Prometheus export pending |

Tenant labels must use tenant IDs and must not contain names, emails, prompts, or other PII. Grafana
dashboards and alert thresholds are not measured/configured yet.

## Phase 3 agent metrics

| Metric | Labels | Source | Status |
|---|---|---|---|
| `inventory_stockout_forecast_total` | tenant, outcome | Inventory agent | instrumentation pending |
| `inventory_reorder_proposal_total` | tenant, approval_required | Inventory agent | instrumentation pending |
| `pricing_recommendation_total` | tenant, approval_required | Pricing agent | instrumentation pending |
| `logistics_delay_assessment_total` | tenant, outcome | Logistics agent | instrumentation pending |
| `support_answer_draft_total` | tenant, evidence_found | Support agent | instrumentation pending |
| `support_escalation_draft_total` | tenant | Support agent | instrumentation pending |

These proposed business metrics have no live exporter or dashboard yet. The Phase 3 fake benchmark
measures only serial in-process operation latency and is not a business outcome or production SLO.

## Benchmark status

The synthetic supervisor graph benchmark has been run: 500 serial runs across five route cases,
100% completion, p50 4.43 ms, p95 11.66 ms, p99 21.10 ms, 198 mean synthetic tokens, and zero tool
calls. These figures exclude database checkpoints and queue delivery. Real Gemini latency/tokens/cost,
production agent actions, concurrency, queue throughput, and recovery time are **not measured yet**.
The local PostgreSQL checkpoint integration test verifies process termination and resume behavior,
but it does not report recovery performance.
