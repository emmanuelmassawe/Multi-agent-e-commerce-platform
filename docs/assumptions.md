# Assumptions and unresolved product inputs

## Phase 0

- Read all files under `docs/my-docs/` on 2026-11-18. The folder contains its README and unfilled requirements and business-rules templates; no merchant policies or integration priorities have been supplied.
- Keep the implementation within the stack explicitly prescribed by `AGENTS.md` and `CODEX_MASTER_PROMPT.md`. ADRs 0004 and 0007 were reviewed and accepted for Phase 1; the Phase 1 identity and persistence decision is recorded in ADR 0014.
- Use placeholder local-only credentials in Compose so a developer can start dependencies. Replace them before any shared or deployed environment; no real secrets are included.
- API readiness in the scaffold reports process readiness only. Dependency-aware checks belong with persistence and service wiring in later phases.
- `docker compose config` and YAML parsing succeed, but `docker compose up --build -d` could not complete image pulls: the configured registry returned an authorization error, and dependent pulls were interrupted. Stack health and HTTP checks remain unverified.
- No benchmark has been run; performance and cost figures are **not measured yet**.

## Product decisions still needed

Target countries and languages, first commerce/carrier integrations, model providers and budget, approval thresholds, retention periods, and data residency are unspecified. Record those decisions in `docs/my-docs/` before implementing product policies or selecting a cloud region.

## Phase 1

- A user belongs to one tenant. The login form accepts `tenant_slug` only to locate the candidate identity; authorization scope is loaded from the matched user and signed token.
- The API database role is `clos_app`, a non-superuser role. `DATABASE_ADMIN_URL` is reserved for migrations and controlled seeding.
- Local unit tests use SQLite for repository filtering; raw-session RLS verification uses the PostgreSQL service in CI. Docker image pull failures from Phase 0 mean the PostgreSQL test has not yet run in this local workspace.

