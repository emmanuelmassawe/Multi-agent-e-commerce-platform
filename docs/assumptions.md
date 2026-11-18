# Assumptions and unresolved product inputs

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

