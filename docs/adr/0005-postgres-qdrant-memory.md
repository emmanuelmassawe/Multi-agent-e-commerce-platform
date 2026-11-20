# 0005. Postgres source of truth with derived Qdrant index

- Status: accepted
- Date: 2026-11-18

## Context

Customer and merchant documents require durable metadata, tenant-filtered retrieval, deletion propagation, and rebuildable vector search.

## Decision drivers

Data integrity, tenant isolation, deletion/export compliance, retrieval quality, and rebuildability.

## Options considered

- Postgres as source of truth with Qdrant as a derived index.
- Store authoritative document state only in the vector database.

## Evidence

The supplied vector-memory rule mandates the first option. See the [Phase 5 retrieval measurements](../benchmarks.md).

## Decision

Keep source text in Postgres and rebuild Qdrant using the outbox and tenant reindex job.

## Consequences

ADR 0017 specifies the implemented projection and erasure workflow.

