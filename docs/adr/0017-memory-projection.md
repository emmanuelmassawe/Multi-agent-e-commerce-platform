# 0017. Customer memory projection

## Status
Proposed for Phase 5. Implements the storage boundary in ADR 0005.

## Context
Support needs shared merchant policy and private customer documents. Source text can contain personal data. The owner has not selected a hosted embedding model.

## Decision drivers
Customer isolation, offline operation, reproducible rebuilds and recovery after a worker crash.

## Options considered
Hosted semantic embeddings require a data transfer decision. Local feature hashing plus BM25 term saturation and Qdrant IDF permits an initial offline retrieval baseline. Storing plaintext in both databases duplicates personal data.

## Decision
Use local signed feature hashing and sparse term weights, reciprocal rank fusion in Qdrant, and authoritative SQL hydration. The index holds vectors, scoped IDs and a content digest. Accept plain text only. Generate deterministic chunk IDs and serialize projection jobs per tenant. Poll the durable Postgres outbox from Celery Beat. Require explicit memory management permission for private exports, ingestion and deletion. Hash idempotency keys with the tenant namespace and retain a receipt after deletion.

## Consequences
Lexical hashing is not a trained semantic model. Reindex into a separately named collection before switching models of different dimensionality. Shared policies are searchable alongside customer-specific passages. Index updates are eventually consistent. Erasure is complete only after all memory stores acknowledge it.
