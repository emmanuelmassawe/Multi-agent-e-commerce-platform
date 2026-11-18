# Key sequences

## Run lifecycle

```mermaid
sequenceDiagram
  actor M as Merchant
  participant API
  participant Q as Queue
  participant W as Worker / graph
  participant DB as Postgres
  M->>API: POST /v1/runs
  API->>DB: persist run and outbox event
  API->>Q: enqueue run_id
  API-->>M: 202 Accepted + run_id
  Q->>W: deliver task
  W->>DB: checkpoint state and events
  M->>API: GET /v1/runs/{id}/events
  API-->>M: SSE run events
```

## HITL approval and resume

```mermaid
sequenceDiagram
  participant G as Agent graph
  participant A as Approval service
  actor H as Authorized human
  participant DB as Postgres checkpoint
  G->>A: request write_high approval
  A->>DB: persist approval request and audit record
  G->>DB: checkpoint and interrupt
  H->>A: approve or reject
  A->>DB: persist decision
  A->>G: resume with explicit decision
  G->>G: execute only if approved and policy still permits
```

## Shipment delay cross-agent flow

```mermaid
sequenceDiagram
  participant L as Logistics agent
  participant S as Support agent
  participant R as Rules / approval
  participant C as Customer channel
  L->>L: detect delay from carrier event
  L->>S: provide tenant-scoped shipment facts
  S->>S: draft notice from approved policy
  S->>R: classify message action risk
  R-->>S: approval required when bulk/high risk
  S->>C: send only after authorization
```

## RAG ingestion and retrieval

```mermaid
sequenceDiagram
  participant U as Merchant
  participant API
  participant PG as Postgres
  participant O as Outbox worker
  participant Q as Qdrant
  participant A as Support agent
  U->>API: upload document
  API->>PG: store source, chunks, tenant metadata
  PG->>O: emit outbox event
  O->>Q: idempotent tenant-scoped upsert
  A->>PG: authorize and resolve tenant scope
  A->>Q: hybrid query with mandatory tenant filter
  Q-->>A: ranked chunks
```

## Outbox synchronization

```mermaid
sequenceDiagram
  participant W as Writer
  participant PG as Postgres transaction
  participant O as Outbox dispatcher
  participant Q as Qdrant
  W->>PG: update document and append outbox event atomically
  O->>PG: claim pending event
  O->>Q: idempotent upsert or delete
  Q-->>O: acknowledge
  O->>PG: mark event delivered
```

## Crash recovery

```mermaid
sequenceDiagram
  participant Q as RabbitMQ
  participant W1 as Worker A
  participant PG as Postgres checkpoint
  participant W2 as Worker B
  Q->>W1: deliver run
  W1->>PG: persist graph checkpoint
  W1--xW1: process crash
  Q->>W2: retry task
  W2->>PG: load latest checkpoint
  W2->>W2: resume from checkpoint with idempotency keys
```

Phase 2 validates recovery by interrupting after the classification checkpoint, terminating the
worker subprocess, starting a replacement process, and resuming the same tenant/run thread from
PostgreSQL. Recovery latency is not measured yet.

