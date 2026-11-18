# 0007. Tenant isolation with PostgreSQL row-level security

- Status: accepted
- Date: 2026-11-18

## Context

The platform is multi-tenant and every tenant-owned record must be inaccessible across tenant boundaries.

## Decision drivers

Isolation strength, defense in depth, repository ergonomics, auditability, and testability.

## Options considered

- Tenant-scoped repositories plus PostgreSQL RLS.
- Application-level filters without database row policies.

## Evidence

The supplied security rule requires RLS. No isolation tests have been implemented yet.

## Decision

Record tenant-scoped repositories and RLS as proposed.

## Consequences

Phase 1 must prove isolation through API, repositories, and raw sessions.

## Review

The Phase 1 schema applies forced PostgreSQL RLS to every tenant-owned table and uses an explicit non-superuser application role. Repository predicates add defense in depth. The real PostgreSQL test runs in CI; local execution depends on a reachable database.

