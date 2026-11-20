# Assumptions and unresolved product inputs

## Phase 4

- Read all files under `docs/my-docs/` at phase start on 2026-11-19. Approval approvers, channels,
  and expiration durations are still unspecified. API approval access follows existing RBAC
  `manage_approvals` permission (manager and agent-operator roles); no additional approver role is
  inferred.
- `APPROVAL_EXPIRY_SECONDS` is required before a new `write_high` approval can be requested. No
  default expiration duration is invented. Expired approvals are auto-rejected, audited, and their
  graph resumes with a rejection.
- Dashboard approval notifications stream persisted tenant-scoped audit events over SSE. Email and
  WhatsApp are notification ports with deterministic fakes only; the owner has not selected providers
  or recipients, so no external message is sent.
- `PATCH /v1/approvals/{approval_id}` modifies only the validated tool input and approves that exact
  input. The resumed tool validates it again and verifies the database record before execution.
- Approval API and resume tasks are implemented, but Phase 3 did not wire provider-backed agent
  runners into the worker. Production tool execution therefore still requires those runners to be
  configured; the HITL gate itself fails closed without a requester, interrupt, and persisted verifier.
- PostgreSQL migration 0003 adds a nullable tool idempotency key to existing approval rows. Approval
  context may contain confidential business or personal data and remains classified accordingly in
  the compliance inventory.
- Migration 0003 upgraded, downgraded, and upgraded again on the local PostgreSQL 16 instance.
  Approval, tenant-isolation, tool-idempotency, and checkpoint-recovery PostgreSQL integration tests
  passed on 2026-11-19. CI/local Mermaid rendering remains unavailable because `mmdc` is not installed.
- Approval processing and resume latency are not benchmarked yet. Prometheus exporters and Grafana
  approval panels remain pending; the event stream uses durable audit rows.

## Phase 0

- Read all files under `docs/my-docs/` on 2026-11-18. The folder contains its README and unfilled requirements and business-rules templates; no merchant policies or integration priorities have been supplied.
- Keep the implementation within the stack explicitly prescribed by `AGENTS.md` and `CODEX_MASTER_PROMPT.md`. ADRs 0004 and 0007 were reviewed and accepted for Phase 1; the Phase 1 identity and persistence decision is recorded in ADR 0014.
- Use placeholder local-only credentials in Compose so a developer can start dependencies. Replace them before any shared or deployed environment; no real secrets are included.
- API readiness in the scaffold reports process readiness only. Dependency-aware checks belong with persistence and service wiring in later phases.
- `docker compose config` and YAML parsing succeed. During Phase 1, the PostgreSQL 16 image was pulled and started; PostgreSQL health and tenant RLS were then verified locally.
- No benchmark has been run; performance and cost figures are **not measured yet**.

## Product decisions still needed

Target countries and languages, first commerce/carrier integrations, model providers and budget, approval thresholds, retention periods, and data residency are unspecified. Record those decisions in `docs/my-docs/` before implementing product policies or selecting a cloud region.

## Phase 1

- A user belongs to one tenant. The login form accepts `tenant_slug` only to locate the candidate identity; authorization scope is loaded from the matched user and signed token.
- The API database role is `clos_app`, a non-superuser role. `DATABASE_ADMIN_URL` is reserved for migrations and controlled seeding.
- Local unit tests use SQLite for repository filtering; raw-session RLS verification has passed against local PostgreSQL 16. The older Phase 0 note about image pulls is superseded by this verification.

## Phase 2

- Read all files under `docs/my-docs/` at phase start on 2026-11-18; the requirement and business-rule templates were blank then. A later owner edit specified Gemini free tier and fallback API keys. CLOS now uses a Gemini adapter behind `LLMPort`, with environment-only key rotation. No key value was supplied or stored in the repository.
- Tests use deterministic synthetic responses only; synthetic token/cost records are never represented as real provider measurements. Free-tier requests may be used to improve Google products; direct email, phone-number, and credential-shaped strings are redacted, but this is not full PII detection. Avoid customer-confidential prompts until the privacy controls are reviewed.
- PostgreSQL checkpoint thread IDs are derived as `<tenant_uuid>:<run_uuid>` to scope reads and writes. The checkpointer's internal tables are not tenant-row-RLS tables; app code must only construct checkpoint configs through `checkpoint_config`.
- Supervisor routing and checkpoint resume are implemented and the PostgreSQL recovery test terminates and replaces a worker subprocess. Recovery latency is not measured yet. Business agent actions remain Phase 3; a public run-submission endpoint is not part of this slice.
- The full Compose startup was attempted but could not pull `quay.io/minio/minio:latest` (registry returned HTTP 401); services beyond the already-running PostgreSQL container remain unverified. OpenAPI/AsyncAPI YAML parses, but Spectral, AsyncAPI CLI, and Mermaid rendering were not run locally because Node.js/npm/mmdc are unavailable.

## Phase 3

- Read all files under `docs/my-docs/` at phase start on 2026-11-18. Gemini free tier and fallback API keys are specified, but the business-rules template remains unfilled. There are no thresholds, margin rules, carrier allowlists, delay windows, reorder policies, support languages/tone, or escalation contacts to encode.
- Agent calculations accept tenant rules and operational facts as inputs. Missing thresholds are not inferred: stockout coverage is descriptive, delay detection reports unknown without required timestamps, and price recommendations remain approval-required unless an explicit threshold makes the delta in-rule.
- External commerce, competitor-price, carrier, and support retrieval systems have no selected providers. Phase 3 defines tenant-scoped ports and deterministic fakes. No customer notification is sent; support answers are drafts.
- Write actions remain blocked unless existing tool policy receives a valid persisted approval. The Phase 4 graph interrupt/approval/resume lifecycle is not implemented yet; Phase 3 produces reorder, price, and rebooking proposals without executing them.
- Customer-scoped support retrieval requires `customer_id` in trusted agent context. Tenant and customer scope are not accepted from the query text. Production adapters must enforce those filters.
- Route choice orders supplied options by cost, then duration. No carrier preference or service-level policy was provided. Shipment timestamp comparison requires compatible ISO 8601 UTC timestamps; a configurable delay window remains outstanding.
- Pricing accepts an explicit stockout-risk signal and optional merchant stockout markup. With no configured markup, no price change is inferred from inventory risk; threshold detection remains an input from an inventory policy.
- Agent prompts are versioned. Evals use deterministic synthetic data; no real customer data or real LLM evaluation was used. Agent latency and business outcomes are not measured yet.
- Mermaid source was updated, but local rendering validation remains unavailable because the `mmdc` executable is not installed; CI is configured to render these diagrams.

## Phase 5

The owner's files contain no approved support corpus, embedding provider, residency rule or retention schedule. This phase accepts plain text and uses local lexical features so retrieval sends no personal data to an embedding provider. Only an owner, using a suitably scoped credential, can manage customer memory. A document without a customer ID is an explicitly shared tenant policy. Real merchant-language quality has not been measured.
