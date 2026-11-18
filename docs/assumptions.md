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

- Read all files under `docs/my-docs/` on 2026-11-18. Only the README, empty directories, and unfilled requirement/business-rule templates are present; no provider, merchant policy, or budget values were specified.
- The LLM provider adapter remains provider-neutral until a vendor and credentials are supplied. Tests use deterministic synthetic responses only; synthetic token/cost records are never represented as real provider measurements.
- PostgreSQL checkpoint thread IDs are derived as `<tenant_uuid>:<run_uuid>` to scope reads and writes. The checkpointer's internal tables are not tenant-row-RLS tables; app code must only construct checkpoint configs through `checkpoint_config`.
- Supervisor routing and checkpoint resume are implemented. Business agent subgraphs and production provider integration remain later implementation slices; process-level worker-kill recovery is not measured yet.

