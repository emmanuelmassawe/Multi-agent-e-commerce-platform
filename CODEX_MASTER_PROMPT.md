# Master Prompt for Codex (paste into Codex in VS Code)

Read AGENTS.md first and follow it strictly. Build the platform in the phases below.
Complete ONE phase at a time. After each phase: run all quality gates, fix failures,
summarize what was done, list assumptions, then stop and wait for me to say "next phase".

## Before every phase
Read everything in `docs/my-docs/` (owner's documentation) and use it as requirements/context.
Never modify, rename or delete files there. If it conflicts with AGENTS.md or this prompt, record the
conflict and your interpretation in `docs/assumptions.md` and mention it in the phase summary.

## Product
CLOS is a multi-tenant platform for online merchants. Merchants cannot track shipments,
set competitive prices, and answer customers at the same time. CLOS runs four agents
coordinated by a Supervisor so these happen continuously, with humans approving risky actions.

## Repository layout to create
```
clos/
  apps/
    api/                 # FastAPI app (HTTP, SSE, WebSocket)
    worker/              # Celery workers
    web/                 # Next.js dashboard
  src/clos/
    domain/              # entities, value objects, domain events, policies (pure Python)
    application/         # use cases, ports (interfaces), DTOs
    agents/
      supervisor/        # router graph
      inventory/ pricing/ logistics/ support/   # subgraphs + tools
      memory/ guardrails/ budgets/ hitl/
    adapters/
      db/ cache/ queue/ llm/ vector/ observability/
      integrations/      # shopify, woocommerce, carriers, competitor_prices, whatsapp, email (+ fakes)
      sandbox/
    config/ security/
  prompts/               # versioned prompt files per agent
  evals/                 # golden datasets + eval tests
  migrations/            # Alembic
  tests/ (unit, integration, e2e, load)
  docs/my-docs/          # OWNER'S documentation: read-only for Codex (never modify or delete)
  deploy/ (docker, compose)
  infra/terraform/ (modules/, envs/dev|staging|prod, README; see Phase 11)
  docs/ (architecture.md, adr/, runbooks/, api.md, assumptions.md)
```

## Cross-cutting requirements (apply to EVERY phase)
### Architecture diagrams (Mermaid, in docs/architecture/, updated in the same change as the code)
- 01-context (C4 L1): merchants, customers, carriers, marketplaces, competitor sources, notification channels
- 02-containers (C4 L2): api, worker, web, postgres, qdrant, redis, rabbitmq, langfuse, prometheus/grafana, sandbox
- 03-components: one per agent (tools, prompts, guardrails, memory access)
- 04-supervisor-graph: LangGraph state diagram (routing, parallel branches, interrupt/resume, budget stop)
- 05-sequences: run lifecycle (202 -> queue -> graph -> SSE), HITL approval/resume, shipment-delay cross-agent flow,
  RAG ingestion + retrieval, outbox sync Postgres -> Qdrant, crash-recovery from checkpoint
- 06-erd: full database model with tenant_id and RLS notes
- 07-deployment: local compose vs AWS (VPC, public/private subnets, ALB+WAF, ECS/EKS, RDS, ElastiCache, MQ, Qdrant, S3, NAT/endpoints), scaling units, network zones
- 08-security: trust boundaries, data flows, threat model (STRIDE)
CI validates every Mermaid file renders. Add a README index linking all diagrams.

### API design structure (contract-first; docs/api/)
Deliver before implementing endpoints: `openapi.yaml` (OpenAPI 3.1), `asyncapi.yaml` (SSE/WebSocket/webhook events),
`design-guidelines.md`, and `changelog.md`. Lint with Spectral; contract tests (Schemathesis) in CI.
Conventions:
- Base path `/v1`; resource nouns, plural, snake_case JSON; UUIDv7 ids; RFC 3339 UTC timestamps
- Resource map: /auth, /tenants, /users, /products, /inventory, /warehouses, /suppliers, /orders, /shipments,
  /carriers, /price-rules, /price-recommendations, /competitors, /customers, /conversations, /messages,
  /documents (RAG), /reports, /runs (agent runs), /approvals, /integrations, /webhooks, /usage (tokens/cost), /audit-logs, /health
- Long-running work: `POST /v1/runs` -> `202` + `run_id` + `Location`; `GET /v1/runs/{id}`; `GET /v1/runs/{id}/events` (SSE);
  `POST /v1/runs/{id}/cancel`
- Approvals: `GET /v1/approvals`, `POST /v1/approvals/{id}/approve|reject`, `PATCH` to modify before approving
- Cursor pagination (`limit`, `cursor`, `next_cursor`), filtering (`filter[field]=`), sorting (`sort=-created_at`)
- Errors: RFC 9457 problem+json with stable `code`, `trace_id`, field-level validation details; documented per endpoint
- Idempotency-Key on all POSTs that mutate; ETag/If-Match on updates; rate-limit headers and `429` with `Retry-After`
- Auth: OAuth2/JWT bearer + API keys for integrations; scopes per RBAC role; tenant derived from token, never from request body
- Webhooks: HMAC-signed, timestamped, retried with backoff, replay endpoint, event catalog in AsyncAPI
- Versioning/deprecation: additive changes only within a version; breaking change = new version + ADR; `Sunset` and `Deprecation` headers
- Every endpoint documents: auth scope, request/response schema with examples, error codes, idempotency, rate limit class

### ADR process (docs/adr/)
Add `docs/adr/README.md` with the steps and `0000-template.md` (MADR). Steps for every decision:
1. Identify the decision and why it must be made now
2. List decision drivers (latency, cost, ops burden, security, team skills) and options (at least 2)
3. Gather evidence: spike or benchmark with real, reproducible numbers (no invented figures)
4. Draft ADR with status `proposed`
5. Review and discuss; record dissenting views
6. Set status `accepted`; implement; link the ADR from code, diagrams and docs
7. If later changed: create a new ADR and mark the old one `superseded by NNNN` (never delete)
Maintain `docs/adr/index.md`. Initial ADRs to write in Phase 0:
0001 record decisions, 0002 Python/FastAPI, 0003 LangGraph + Postgres checkpointer, 0004 Hexagonal architecture,
0005 Postgres source of truth + Qdrant derived index, 0006 Celery+RabbitMQ vs Temporal, 0007 multi-tenancy with RLS,
0008 HITL via interrupt + approvals, 0009 API contract-first and versioning, 0010 observability stack (Langfuse + OTel + Prometheus),
0011 guardrails approach, 0012 sandbox execution strategy, 0013 LLM provider abstraction and fallback.

### Safe autonomy (shadow mode, kill switch, explainability)
- Autonomy mode per tenant and per agent: `off | shadow | assisted | autonomous`; default `shadow` for new tenants/agents
- Shadow mode: agents run fully but never execute writes; store proposals and later compare with the human's actual action; report agreement rate per agent (measured, never estimated)
- Promotion between modes is audited and restricted to owner role; automatic demotion to `assisted` if error/rejection rate crosses a configured threshold
- Kill switch: global and per-tenant, via dashboard, `POST /v1/admin/kill-switch`, and runbook; cancels in-flight runs at next checkpoint, pauses Celery beat jobs, blocks all writes; tests prove no write executes while active
- Decision explanations stored per action (inputs, rule, alternatives) and shown in the dashboard and approval requests
- Add the autonomy and kill-switch endpoints to OpenAPI, an ADR, a sequence diagram, and metrics (`autonomy_mode`, `shadow_agreement_ratio`, `kill_switch_active`)

### Compliance and data protection (docs/compliance/)
- Deliver drafts (for legal review) of: data inventory + data-flow map, PII classification per table/column/vector payload,
  retention schedule (with enforcing jobs), consent/lawful-basis model, DSAR export/delete runbook across Postgres, Qdrant, Redis, S3, logs and backups,
  privacy policy and DPA templates, sub-processor list, breach notification procedure, applicable-law matrix (GDPR, Tanzania PDPA, Kenya DPA, others from docs/my-docs/)
- Data residency: choose AWS region and LLM provider region by ADR based on those requirements
- PII minimization before LLM calls and tracing; tests that PII never reaches logs/traces
- Not legal advice: every document carries a "needs legal review" banner

### Benchmarks (benchmarks/ directory, `make bench`)
All numbers must be measured, never invented or estimated. Each result file records: date, git SHA,
hardware/OS, dataset size, tool versions, exact command, and whether the LLM was real or fake.
- api: k6/Locust scenarios (create run, stream SSE, approvals) at several concurrency levels -> RPS, p50/p95/p99, error rate
- agents: end-to-end latency, success rate, tool calls and tokens per run, for each agent and for cross-agent flows
- llm: real-provider runs (latency, tokens, cost per run) kept separate from fake-LLM runs; fake runs labeled "synthetic"
- retrieval: recall@k, MRR, p50/p95 latency on a seeded dataset with tenant filter, dense vs hybrid, at 10k/100k/1M chunks
- queue: throughput, queue depth, time-in-queue, worker scaling 1/2/4/8
- database: key query p95, pool saturation, RLS overhead
- resilience: time to resume after worker kill, behavior during Qdrant/DB outage
Output: `benchmarks/results/<date>-<sha>.json` + generated `docs/benchmarks.md` with tables and charts.
If something has not been run, docs must say "not measured yet". CI compares against a baseline and fails on regressions beyond thresholds in `benchmarks/thresholds.yaml`.

### Metrics (docs/metrics.md + Grafana dashboards as code)
- RED metrics per endpoint; agent_run_duration_seconds, agent_run_success_total, tool_call_duration_seconds, tool_call_errors_total
- llm_tokens_total (in/out) and llm_cost_usd_total per tenant/agent/model; budget_exceeded_total
- approvals_pending, approval_latency_seconds, approval_outcome_total
- queue_depth, task_wait_seconds, dlq_size; retrieval_latency_seconds, retrieval_empty_total; outbox_lag_seconds, qdrant_drift_total
- guardrail_blocked_total by rule; business KPIs: stockouts prevented, price changes applied, shipments delayed/recovered, support resolution rate
- SLOs with alert rules (error budget burn, stuck runs, outbox lag)
Dashboards: API health, agent performance, cost per tenant, queue/workers, retrieval, business KPIs.

## Phase 0 — Foundation
- Monorepo scaffold, uv project, ruff/mypy/pre-commit, Dockerfiles, docker-compose
  (api, worker, postgres, qdrant, redis, rabbitmq, langfuse, prometheus, grafana).
- Config via pydantic-settings; structured logging; health endpoints; GitHub Actions CI running all gates.
- docs/architecture/ diagrams, docs/api/ skeleton (openapi.yaml, design-guidelines.md), and the initial ADRs 0001-0013 with the ADR README and template.

## Phase 1 — Core domain & persistence
- Entities: Tenant, User, Product, InventoryItem, Warehouse, Supplier, Order, Shipment,
  ShipmentEvent, Carrier, PriceRule, PriceSnapshot, CompetitorListing, Customer, Conversation,
  Message, ApprovalRequest, AgentRun, ToolCall, AuditLog, TokenUsage.
- Alembic migrations, async repositories, Row-Level Security by tenant_id, seed script.
- Auth: JWT + refresh, RBAC, API keys for integrations.
- Tests proving tenant isolation.

## Phase 2 — Agent runtime & orchestration
- LangGraph Supervisor graph with Postgres checkpointer: classify intent -> route to subgraph(s)
  (parallel where independent) -> aggregate -> respond. Resume after crash from last checkpoint (test it by killing the worker mid-run).
- Typed tool registry with risk levels, schema validation, idempotency, timeouts, retries.
- LLMPort with provider adapter + fallback; deterministic fake LLM for tests.
- Budget enforcer (tokens, steps, tool calls, wall-clock) with hard stop + TokenUsage records.

## Phase 3 — The four agents
- Inventory Agent: tools read_stock_levels, forecast_stockout, propose_reorder (write_high -> HITL).
- Pricing Agent: tools fetch_competitor_prices, compute_price_recommendation (respect min margin,
  floor/ceiling PriceRules), apply_price_change (auto if within rule, HITL if above threshold).
- Logistics Agent: tools track_shipment, detect_delay, plan_route/select_carrier (cost/time tradeoff),
  rebook_shipment (HITL when cost increase > threshold).
- Support Agent: RAG over policies/FAQ/order history, answer_customer, generate_report (daily sales/shipment/inventory),
  escalate_to_human. Must never reveal other customers' or other tenants' data.
- Each agent has prompts in prompts/, golden evals in evals/, and integration tests with fakes.
- Cross-agent flows: e.g. shipment delay -> Support drafts customer notice; stockout risk -> Pricing considers raising price.

## Phase 4 — Human-in-the-Loop
- `interrupt` before every write_high tool; create ApprovalRequest with full context, diff, risk, expiry.
- Notification adapters: dashboard (SSE), email, WhatsApp (Twilio/Meta Cloud API behind port, with fake).
- Endpoints: list/approve/reject/modify-and-approve; graph resumes with decision; timeout -> auto-reject + audit.
- Tests: no write_high action can execute without an approved ApprovalRequest.

## Phase 5 — Memory & RAG
- Short-term: Redis (session) + Postgres (conversation history), summarization when long.
- Long-term: Qdrant behind `VectorStorePort` (`QdrantVectorStore` adapter + in-memory fake for tests).
  Postgres stores documents, chunks and metadata as source of truth; Qdrant is a derived index.
- Sync Postgres -> Qdrant via outbox events handled by an idempotent worker; include a full reindex job
  (also used when changing the embedding model) and a drift-check job comparing counts/checksums.
- Chunking, tenant-filtered retrieval (mandatory `tenant_id` filter in the repository, payload index on tenant_id),
  hybrid search (dense + sparse BM25/SPLADE with fusion inside Qdrant), document ingestion pipeline
  (upload -> parse -> chunk -> embed in background job).
- Per-customer memory with PII controls; delete/export endpoints that remove data from BOTH Postgres and Qdrant, with audit log.
- Tests: cross-tenant leakage test on retrieval, outbox idempotency, reindex produces identical results, delete propagation.

## Phase 6 — Async backend & real-time
- POST /v1/runs returns 202 + run_id; Celery executes graph; GET /v1/runs/{id}/events via SSE streams
  node/tool/token events; WebSocket for approvals inbox. Idempotency-Key support.
- Scheduled jobs (Celery beat): periodic inventory scan, competitor price refresh, shipment polling.
- Webhooks inbound (Shopify orders, carrier tracking) with signature verification + outbox for outbound events.
- Rate limiting per tenant/user (Redis), DLQ + replay tooling.

## Phase 7 — Guardrails & security
- Input guardrails: prompt-injection detection, PII detection, topic restrictions. Output guardrails:
  schema validation, secret/PII leak filter, policy checks (no unapproved discounts, no legal/medical claims).
- Treat all tool outputs and retrieved docs as untrusted data (never instructions).
- Sandbox runner for any code-execution/data-analysis tool: Docker, no network, CPU/mem/time limits, read-only FS.
- Red-team test suite (injection, data exfiltration, cross-tenant probing) in evals/.
- Dependency audit, SAST (bandit), secret scanning in CI.

## Phase 8 — Observability & evaluation
- Langfuse tracing for every run (agent, tool, LLM spans, cost, latency) + OpenTelemetry for API/worker.
- Prometheus metrics + Grafana dashboards: run latency, success rate, approval rate, token cost per tenant, queue depth.
- Eval harness: golden datasets per agent, LLM-as-judge + deterministic checks, regression gate in CI.
- Alerts for budget breaches, error spikes, stuck runs.

## Phase 9 — Dashboard (Next.js)
- Login, tenant switcher, KPI overview, shipments map/table, inventory alerts, price recommendations,
  approvals inbox (approve/reject/edit), live run trace viewer, conversation console, settings (budgets, rules, integrations).

## Phase 10 — Production hardening
- Container hardening (non-root, minimal images, SBOM, image scanning), worker autoscaling policy, readiness/liveness (AWS infra is Phase 11; Kubernetes/Helm only if the ADR chooses EKS), graceful shutdown, zero-downtime migrations,
  backup/restore runbook (Postgres PITR + Qdrant snapshots, plus reindex-from-Postgres recovery path), load tests (include p95 of retrieval with tenant filter) (k6/Locust) with target p95 and concurrency documented,
  chaos tests (kill worker, DB failover), SLOs, runbooks, threat model, README quickstart.

## Phase 11 — AWS deployment with Terraform (final phase)
Write ADRs first (ECS Fargate vs EKS — default ECS Fargate unless evidence says otherwise; Qdrant self-hosted vs Qdrant Cloud;
Amazon MQ vs self-run RabbitMQ; Langfuse self-hosted vs cloud; LLM provider via Bedrock vs external API).
Layout:
```
infra/terraform/
  modules/ network | ecr | ecs-cluster | ecs-service | rds-postgres | elasticache-redis | amazon-mq | qdrant
          | s3 | alb-waf | dns-acm | secrets-kms | observability | iam-oidc | autoscaling | backup
  envs/ dev | staging | prod   (backend.tf, main.tf, variables.tf, terraform.tfvars.example, outputs.tf)
  bootstrap/  (S3 state bucket + locking, KMS, GitHub OIDC role)
  README.md   (how to bootstrap, plan, apply, destroy dev, rollback)
```
Resources and requirements:
- Region: chosen by ADR from the data residency requirements in docs/compliance/ (not defaulted)
- Network: VPC across 3 AZs, public subnets (ALB only), private app subnets, isolated data subnets, VPC endpoints (ECR, S3, Secrets Manager, CloudWatch) to limit NAT cost, security groups with least privilege
- Edge: Route53, ACM TLS, ALB with WAF (rate limits, managed rules), HTTPS only, SSE-friendly idle timeouts
- Compute: ECR repos (immutable tags, scan on push), ECS services for api, worker, beat, web; Qdrant on dedicated service with EBS/EFS persistence and snapshots to S3; autoscaling on CPU, queue depth and request count; graceful shutdown and deployment circuit breaker with rollback
- Data: RDS PostgreSQL Multi-AZ (prod), encrypted, PITR, parameter group tuned, RDS Proxy optional; ElastiCache Redis with auth/TLS; Amazon MQ RabbitMQ (cluster in prod); S3 for documents/reports/backups with versioning, lifecycle, block public access
- Security: KMS keys, Secrets Manager with rotation, IAM task roles least privilege, GuardDuty/Config/CloudTrail enabled, no public DB, optional Bedrock access via VPC endpoint
- Observability: CloudWatch logs/alarms, ADOT/OTel collector, Prometheus/Grafana (AMP/AMG or self-hosted), alarms wired to the SLOs and to SNS/email/Slack
- CI/CD: GitHub Actions with OIDC (no static keys): build -> test -> scan -> push to ECR -> terraform plan on PR -> auto-apply dev -> manual approval for staging/prod -> run migrations as a one-off task -> smoke tests -> rollback on failure
- Environments: dev (cheap, single-AZ, can be destroyed), staging (prod-like), prod (Multi-AZ, deletion protection, backups)
- Quality: `terraform fmt/validate`, `tflint`, `checkov`, Terratest or `terraform test` for key modules, `infracost` estimate per env in docs/costs.md (real tool output only), tagging policy, drift detection scheduled job
- Docs: AWS deployment diagram, runbooks (deploy, rollback, scale, restore RDS/Qdrant, rotate secrets, disaster recovery with documented RPO/RTO measured in a drill), and a go-live checklist
- Re-run the benchmark suite against staging on AWS and record real results in docs/benchmarks.md

## Phase 12 — Commercial readiness (billing, access security, operations)
Write ADRs first (billing provider, SSO approach, status page/on-call tooling).
- Tenant onboarding and billing: self-service signup, onboarding wizard (connect store, set price rules and approval thresholds, upload policies, start in shadow mode),
  plans and limits (runs, tokens, seats), usage metering from TokenUsage/AgentRun, invoicing and subscriptions via a billing provider behind `BillingPort`
  (Stripe and/or local mobile-money options per docs/my-docs/, with fakes), dunning, plan enforcement, per-tenant cost vs revenue report (real data only)
- Access security: MFA (TOTP), SSO via OIDC/SAML for larger tenants, API key lifecycle (create, scope, rotate, revoke, last-used), session management, brute-force protection, audit of admin actions
- Security assurance: threat model review, dependency and container scanning gates, penetration test plan and checklist, vulnerability disclosure policy
- Operations: on-call rota template, severity levels, incident response runbook, post-mortem template, public status page, customer SLA draft tied to measured SLOs, support playbooks
- Language and market: Kiswahili and English support in Support Agent prompts, dashboard i18n, multi-currency and tax settings, locale-aware dates/numbers; extra markets and carriers/payments from docs/my-docs/
- Backlog (not required now, record in docs/backlog.md): feature flags, FinOps budgets/alarms per tenant, BI/analytics warehouse, PWA/mobile, WhatsApp as a full customer channel, demo tenant with seed data, CONTRIBUTING/devcontainer/release process

## Definition of Done (every phase)
Code + tests + docs + passing CI gates + OpenAPI/AsyncAPI updated first and contract tests passing + ADR written for each significant decision + updated architecture diagrams + relevant benchmarks run
(with real, reproducible numbers and environment metadata) + metrics/dashboards for new features
+ new write actions respect autonomy modes and the kill switch + new personal-data fields classified in docs/compliance/
+ no TODOs left unexplained + short summary of decisions and remaining risks.

Start now with Phase 0.
