# Phase prompts — paste one at a time after you reviewed the previous phase

## Generic template (use for every phase)
```
next phase: Phase <N>.
Re-read AGENTS.md and docs/my-docs/ first. Follow the Phase <N> section of CODEX_MASTER_PROMPT.md
and all cross-cutting requirements. Before coding, list: the plan, the ADRs you will write,
and any blocking questions (max 5). Then implement, run all quality gates, and finish with the
standard phase report. Stop afterwards.
```

## Phase-specific acceptance checks (append to the generic prompt)

**Phase 0 — Foundation**
`Acceptance: docker compose up gives a healthy stack; /health/live and /health/ready work; CI runs all gates; ADRs 0001-0013 exist; diagrams render; docs/api skeleton lints.`

**Phase 1 — Domain & persistence**
`Acceptance: migrations apply and roll back; RLS enforced; a test proves tenant A can never read tenant B data via API, repository or raw session; JWT + RBAC tests pass.`

**Phase 2 — Agent runtime**
`Acceptance: kill the worker mid-run and show the run resumes from the last checkpoint (real test, real timing); budget enforcer hard-stops an infinite-loop test; tools reject invalid input.`

**Phase 3 — The four agents**
`Acceptance: each agent has prompts in prompts/, golden evals in evals/, fakes-based integration tests; cross-agent flow (shipment delay -> customer notice; stockout risk -> pricing) is tested end to end; Support Agent never leaks other customers' or tenants' data (test).`

**Phase 4 — HITL**
`Acceptance: a test proves no write_high tool can execute without an approved ApprovalRequest, including via retries, resume and direct tool call; timeout auto-rejects; approve/reject/modify all resume correctly. Add autonomy modes (shadow/assisted/autonomous) and the kill switch here if not yet present.`

**Phase 5 — Memory & RAG**
`Acceptance: cross-tenant retrieval leakage test passes; outbox sync is idempotent; reindex gives identical results; delete removes data from Postgres AND Qdrant; drift check works; retrieval benchmark run with real numbers at the dataset sizes you can actually run (state which).`

**Phase 6 — Async backend**
`Acceptance: POST /v1/runs returns 202; SSE streams real events; duplicate Idempotency-Key does not duplicate work; DLQ + replay works; webhook signatures verified; rate limits enforced; API load test run with real numbers.`

**Phase 7 — Guardrails & security**
`Acceptance: red-team suite (prompt injection, exfiltration, cross-tenant probing) in evals/ with results reported honestly, including failures; sandbox has no network and enforced limits (test); SAST, dependency audit and secret scanning run in CI.`

**Phase 8 — Observability & evals**
`Acceptance: every run visible in Langfuse with agent/tool/LLM spans, cost and latency; Prometheus metrics from docs/metrics.md exposed; Grafana dashboards provisioned as code; eval regression gate in CI; alerts defined.`

**Phase 9 — Dashboard**
`Acceptance: approvals inbox, live run trace, KPIs, shipments, inventory alerts, price recommendations, settings, kill switch and autonomy controls; e2e tests (Playwright) for approve/reject flow; accessibility basics checked.`

**Phase 10 — Production hardening**
`Acceptance: non-root minimal images, SBOM and image scan; zero-downtime migration demonstrated; chaos tests (kill worker, DB failover, Qdrant down) with real results; load test with documented p95 and concurrency; runbooks written.`

**Phase 11 — AWS + Terraform**
`Acceptance: write ADRs first (region by data residency, ECS vs EKS, Qdrant hosting, MQ, Langfuse hosting); terraform fmt/validate/tflint/checkov pass for every env; plan reviewable; no secrets in code; OIDC deploy pipeline; infracost output in docs/costs.md. DO NOT run terraform apply against any real AWS account; stop after plan and wait for me.`

**Phase 12 — Commercial readiness**
`Acceptance: onboarding wizard starts tenants in shadow mode; billing behind BillingPort with fakes; MFA and API key lifecycle tested; incident runbooks and status page plan written; Kiswahili/English in Support Agent evals.`

## Review prompts (use between phases)

**Honesty / verification**
```
Audit your last phase. List every claim in your report and the exact command or file that proves
it. Re-run the quality gates now and paste real output. Flag anything you claimed but did not verify.
```

**Security review**
```
Act as an adversarial security reviewer of the code added in this phase. Look for: tenant isolation
gaps, authorization bypass, prompt injection paths, secrets in code/logs, unsafe tool execution,
PII leaking to logs/traces/LLMs. Report findings with file and line, severity, and fix. Then fix the
high-severity ones.
```

**Architecture review**
```
Compare the code with docs/architecture/ diagrams, docs/api/openapi.yaml and the ADRs. List every
drift. Update the docs or the code, whichever is wrong, and explain which.
```

**Stuck / failing gates**
```
Gate X is failing. Show the real error, find the root cause, fix the cause (do not disable or
weaken the check), and rerun. If you must make a trade-off, write an ADR.
```
