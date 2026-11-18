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

## Benchmark status

Agent latency, success rate, tool-call count, real-provider tokens/cost, and recovery time are
**not measured yet**. The local PostgreSQL checkpoint integration test verifies process termination
and resume behavior, but it does not report a performance benchmark.
