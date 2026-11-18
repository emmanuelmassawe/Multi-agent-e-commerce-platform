# 0005. Postgres source of truth with derived Qdrant index

- Status: proposed
- Date: 2026-11-18

## Context

Customer and merchant documents require durable metadata, tenant-filtered retrieval, deletion propagation, and rebuildable vector search.

## Decision drivers

Data integrity, tenant isolation, deletion/export compliance, retrieval quality, and rebuildability.

## Options considered

- Postgres as source of truth with Qdrant as a derived index.
- Store authoritative document state only in the vector database.

## Evidence

The supplied vector-memory rule mandates the first option. Recall and latency are not measured yet.

## Decision

Record Postgres plus derived Qdrant as proposed; require outbox sync and reindex capability.

## Consequences

Phase 5 must implement and test idempotent synchronization and deletion across both stores.

