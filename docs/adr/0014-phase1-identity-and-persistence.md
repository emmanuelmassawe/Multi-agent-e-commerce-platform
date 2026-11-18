# 0014. Phase 1 identity and persistence model

- Status: accepted
- Date: 2026-11-18

## Context

Phase 1 needs durable multi-tenant business entities, tenant isolation, user authentication, refresh sessions, and integration API keys. The owner requirements and business-rules templates are still blank.

## Decision drivers

- Preserve the mandated PostgreSQL 16, SQLAlchemy 2 async, and Alembic stack.
- Keep domain objects independent of web and database libraries.
- Apply database-enforced tenant isolation even when a repository omits its tenant filter.
- Store only password hashes, refresh-token hashes, and API-key hashes.
- Keep merchant-specific defaults configurable; new autonomy settings begin in `shadow`.

## Options considered

- SQLAlchemy 2 async models, explicit tenant repository filters, and PostgreSQL forced RLS.
- Application-only filtering without row security.
- A different persistence or identity stack, requiring a stack-change ADR.

## Evidence

The project instructions prescribe SQLAlchemy, Postgres, tenant-scoped repositories, RLS, JWT, refresh tokens, and RBAC. The PostgreSQL raw-session test is part of CI. No performance benchmark has been run; database performance is **not measured yet**.

## Decision

Use the prescribed async Postgres persistence. A user belongs to one tenant. The login form accepts `tenant_slug` as an identity selector; the API derives authorization scope from the matched user record and signed token. Passwords use Argon2. Access and refresh tokens are HS256 JWTs; refresh JWTs are single-use and their hashes are stored. Integration keys are tenant-prefixed, stored as SHA-256 hashes, permission-limited, and their creation accepts an idempotency key. The app connects as a non-superuser `clos_app` role; RLS context is transaction-local.

## Consequences

- The application must set `app.current_tenant_id` inside each transaction before touching tenant-owned rows.
- PostgreSQL admin credentials are reserved for migrations and seed operations; the API uses the restricted app role.
- Login callers must know the tenant slug. This is a selector only; request bodies never establish an authenticated tenant scope.
- Domain and application tests use fakes or SQLite; RLS proof uses a real Postgres service in CI.
- The initial migration is a frozen PostgreSQL schema snapshot; later revisions must be explicit and must not regenerate this revision.

## Review

Reviewed for alignment with the supplied stack and security requirements before implementation. The owner documents contain no conflicting identity requirements. No dissent recorded.

