# AGENTS.md — Commerce & Logistics Operating System (CLOS)

## Mission
Multi-tenant, production-grade multi-agent platform that lets merchants simultaneously
track shipments, set competitive prices, manage inventory, and answer customers.

## Agents
- Supervisor/Router: classifies intent, routes, aggregates, enforces budgets and HITL.
- Inventory Agent: stock monitoring, low-stock/stockout forecasting, reorder proposals.
- Pricing Agent: competitor price comparison, price change proposals within merchant rules.
- Logistics Agent: shipment tracking, route/carrier planning, delay detection.
- Customer Support Agent: answers customer questions (RAG), produces reports.

## Stack (do not change without an ADR in docs/adr/)
- Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async) + Alembic
- LangGraph (supervisor + subgraphs) with Postgres checkpointer (durable, resumable)
- PostgreSQL 16 (source of truth, conversations, checkpoints); Qdrant (derived vector index for RAG); Redis (short-term memory, cache, rate limit)
- Celery + RabbitMQ for background jobs (Temporal is an acceptable alternative via ADR)
- SSE (primary) and WebSocket for streaming results/approvals
- Langfuse for tracing; OpenTelemetry + Prometheus metrics; structlog JSON logs
- Guardrails: input/output validation + prompt-injection defense (NeMo Guardrails or Guardrails AI behind an interface)
- Sandboxed code execution: Docker-based runner (E2B adapter optional), no network, resource limits
- Frontend: Next.js + TypeScript dashboard (approvals inbox, live agent trace, KPIs)
- Tooling: uv, ruff, mypy --strict, pytest, pytest-asyncio, testcontainers, pre-commit, Docker Compose, GitHub Actions

## Architecture rules
1. Hexagonal/Clean Architecture: `domain` (pure) <- `application` (use cases) <- `adapters` (db, http, llm, carriers). Domain never imports frameworks.
2. Every external system (LLM, Shopify/WooCommerce, carriers, competitor prices, WhatsApp/Email) sits behind a Port interface with a fake implementation for tests.
3. Agents only act through typed Tools; tools validate input with Pydantic, are idempotent, and declare a risk level (`read`, `write_low`, `write_high`).
4. `write_high` actions (price changes above threshold, payments, purchase orders, bulk customer messages) MUST pause the graph via LangGraph `interrupt`, create an `approval_request`, notify a human, and resume only on explicit approval. Never bypass.
5. Multi-tenancy: every table has `tenant_id`; enforce with Postgres Row-Level Security and tenant-scoped repositories. Tests must prove cross-tenant isolation.
6. Reliability: outbox pattern for events, idempotency keys on mutating endpoints and tasks, retries with exponential backoff + jitter, circuit breakers, dead-letter queues.
7. Cost control: per-tenant and per-run token budgets, max graph steps, max tool calls, timeouts; hard-stop with a clear error, never loop.
8. Security: JWT auth, RBAC (owner, manager, agent-operator, viewer), secrets from env/secret manager only, PII redaction in logs/traces, audit log for every agent action and approval.
9. Prompts live in `prompts/` as versioned files, never inline in code. Every prompt change needs an eval run.
11. Vector memory: Postgres is the source of truth for documents, chunks and metadata; Qdrant is a derived index that must be rebuildable at any time from Postgres. Sync via the outbox pattern (idempotent upserts and deletes). Access only through `VectorStorePort`; every query goes through a tenant-scoped repository that always applies the `tenant_id` filter (plus `customer_id` where relevant). Deleting customer/PII data must delete from both Postgres and Qdrant and be recorded in the audit log. Use hybrid search (dense + sparse with fusion). Small tenants share a collection with a tenant payload index; large tenants may get their own collection. A reindex job must exist.
12. Architecture diagrams are mandatory and version-controlled as Mermaid in `docs/architecture/`: C4 context, C4 container, component diagrams per agent, supervisor LangGraph state diagram, sequence diagrams (run lifecycle, HITL approval/resume, shipment-delay cross-agent flow, memory/RAG ingestion + retrieval, outbox sync to Qdrant), ERD, deployment diagram, trust-boundary/threat-model diagram. A change to architecture or flow is not done until the diagrams are updated. CI must validate that all Mermaid files render.
13. Benchmarks and metrics must be REAL and reproducible. Never invent, estimate or copy numbers. Every figure in docs must come from a script in `benchmarks/` or from live metrics, and be stored with: date, git SHA, hardware/environment, dataset size, tool versions, and exact command. If a benchmark has not been run, the docs say "not measured yet". Benchmark categories: API (k6/Locust: RPS, p50/p95/p99, error rate), agent runs (end-to-end latency per agent and per graph, success rate, tool-call count), LLM (latency, tokens in/out, cost per run; fake-LLM runs are labeled as such and never presented as real-LLM numbers), retrieval (Qdrant recall@k, p95 latency with tenant filter, hybrid vs dense-only), queue (throughput, depth, time-in-queue), DB (query p95, connection pool saturation), resume-after-crash time. Regressions beyond a stated threshold fail CI.
14. API design is contract-first. The OpenAPI 3.1 spec in `docs/api/openapi.yaml` is the source of truth and is reviewed before implementation; code must match it (contract tests in CI fail on drift). Follow `docs/api/design-guidelines.md`: versioned base path `/v1`, resource-oriented nouns, consistent naming (snake_case JSON), cursor pagination, filtering/sorting conventions, RFC 9457 problem+json errors with stable error codes, `Idempotency-Key` on mutating calls, `202 Accepted` + `run_id` for long-running work, rate-limit headers, ETag/If-Match for concurrent updates, request IDs/trace IDs on every response, SSE/WebSocket event schemas documented (AsyncAPI), signed webhooks with retries, and a deprecation policy (Sunset header, changelog). Breaking changes require a new version and an ADR.
15. Every significant technical decision requires an ADR in `docs/adr/NNNN-title.md` (MADR template: Context, Decision drivers, Options considered, Decision, Consequences, Status). Follow the ADR steps in `docs/adr/README.md`: identify decision -> list options and criteria -> evidence (benchmark/spike, real numbers only) -> draft with status `proposed` -> review -> `accepted` -> implement and link the ADR from code/docs -> if reversed, mark `superseded by NNNN` (never delete). A PR that changes the stack, a public API contract, data model strategy, security model or agent topology without an ADR must not be merged.
16. All AWS infrastructure is defined in Terraform under `infra/terraform/` (no click-ops). Structure: reusable `modules/` (network, ecr, ecs-service or eks, rds-postgres, elasticache-redis, amazon-mq-rabbitmq, qdrant, s3, alb-waf, dns-acm, secrets-kms, observability, iam-oidc, autoscaling, backup) and per-environment roots `envs/dev|staging|prod`. Rules: remote state in S3 with locking and encryption, pinned provider/module versions, least-privilege IAM, private subnets for data and workloads, encryption at rest (KMS) and in transit, secrets only in Secrets Manager/SSM (never in tfvars or git), mandatory tags (project, env, owner, cost-center), no public databases, Multi-AZ in prod, deletion protection and backups in prod, CI deploys via GitHub Actions OIDC (no long-lived AWS keys). `terraform fmt`, `validate`, `tflint`, `checkov` (or tfsec) must pass, and `terraform plan` output is attached to every infra PR; `apply` to prod requires manual approval. Cost figures come from `infracost` runs, never guessed. Infra decisions (ECS Fargate vs EKS, self-hosted Qdrant vs Qdrant Cloud, Amazon MQ vs self-run RabbitMQ) require ADRs.
17. `docs/my-docs/` is the owner's personal documentation folder (requirements, notes, business rules, meeting notes, API docs of partners, PDFs, screenshots). It is HUMAN-OWNED: Codex must read it at the start of every phase and treat it as extra product context, but must NEVER edit, rename, reorganize or delete anything inside it. If its content conflicts with AGENTS.md or the master prompt, do not silently pick one: record the conflict and the chosen interpretation in `docs/assumptions.md` and mention it in the phase summary. Generated documentation goes elsewhere in `docs/` (architecture/, adr/, api/, runbooks/, benchmarks.md, metrics.md, costs.md, assumptions.md). Never write secrets or real customer data into `docs/`.
18. Safe autonomy: every tenant has an autonomy mode per agent: `off`, `shadow` (agent only proposes; nothing is executed, proposals are logged and compared with what the human did), `assisted` (all writes need approval), `autonomous` (only `write_low` and in-rule actions run automatically; `write_high` still needs approval). New tenants and new agents start in `shadow`. Promotion to a higher mode is an explicit, audited, role-restricted action. A global and per-tenant KILL SWITCH must stop all agent runs and scheduled jobs immediately (in-flight runs are cancelled at the next checkpoint, no new writes execute), be usable from dashboard, API and runbook, and be covered by tests. Every agent decision stores an explanation (inputs used, rule applied, alternatives considered) viewable by the merchant.
19. Compliance and data protection by design: follow GDPR principles and applicable local laws (e.g. Tanzania PDPA, Kenya DPA) as listed in `docs/compliance/`. Required artifacts: data inventory and data-flow map, retention schedule enforced by jobs, PII classification of every column and vector payload, data subject export/delete flows (Postgres, Qdrant, Redis, S3, logs, backups policy), consent and lawful-basis records, DPA and privacy policy templates, sub-processor list (LLM providers, AWS, Langfuse), breach notification procedure, and data residency: the AWS region and LLM provider region are decided by ADR from these requirements. Do not send PII to an LLM or tracing tool unless redaction/minimization rules allow it. Compliance docs are drafts for legal review, never legal advice.
10. LLM provider is abstracted (`LLMPort`) so models can be swapped; support fallback model.

## Quality gates (must pass before any task is "done")
- `uv run ruff check . && uv run ruff format --check . && uv run mypy .`
- `uv run pytest` with coverage >= 85% on domain + application
- Agent evals: `uv run pytest evals/` (golden datasets, tool-call correctness, injection tests)
- `docker compose up` brings the full stack healthy; `/health/live` and `/health/ready` work
- Migrations apply and roll back cleanly
- Terraform: `fmt -check`, `validate`, `tflint`, `checkov` pass for every env; plan is reviewable; modules documented with README and examples
- OpenAPI/AsyncAPI specs lint clean (Spectral) and contract tests pass; any decision-worthy change has an ADR
- Diagrams in `docs/architecture/` are up to date and render; benchmark suite runs (`make bench`) and writes results to `benchmarks/results/` with environment metadata
- Prometheus metrics endpoint exposes the metrics listed in `docs/metrics.md` and Grafana dashboards are provisioned as code

## Working style
- Work in small vertical slices; one PR-sized change at a time; write tests first or alongside.
- Update `docs/` (architecture, ADRs, runbooks) when behavior changes.
- Do not invent credentials or call real third-party APIs in tests; use fakes/recorded fixtures.
- If a requirement is ambiguous, record the assumption in `docs/assumptions.md` and proceed.
