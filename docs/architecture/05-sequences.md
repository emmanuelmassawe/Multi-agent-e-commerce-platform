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
  API-->>M: 202 Accepted + run_id
  participant B as Beat dispatcher
  B->>DB: find tenants with pending jobs
  B->>Q: dispatch tenant drain
  Q->>W: deliver task
  W->>DB: claim oldest available job under tenant scope
  W->>DB: checkpoint state and events
  M->>API: GET /v1/runs/{id}/events
  API->>DB: read journal after Last-Event-ID
  API-->>M: SSE nodes, tool events and token usage
```

## HITL approval and resume

```mermaid
sequenceDiagram
  participant G as Agent graph
  participant A as Approval service
  actor H as Authorized human
  participant DB as Postgres checkpoint
  G->>A: request write_high approval with tool input and diff
  A->>DB: persist request, expiry, and audit record idempotently
  A-->>H: notify through tenant-scoped SSE or WebSocket
  G->>DB: checkpoint and interrupt
  H->>A: approve / reject / modify and approve
  A->>DB: persist decision and audit record
  A->>Q: enqueue tenant/run-scoped resume
  Q->>G: resume with approval ID, decision, and approved input
  G->>A: verify persisted decision and exact input
  A-->>G: allow only current, approved request
  G->>G: execute idempotent tool or return rejected
  A->>DB: auto-reject expired request and audit
  A->>Q: resume with rejection
```

## Shipment delay cross-agent flow

```mermaid
sequenceDiagram
  participant L as Logistics agent
  participant S as Support agent
  participant R as Rules / approval
  participant C as Customer channel
  L->>L: track shipment and compare supplied timestamps
  L->>S: provide tenant/customer-scoped shipment facts
  S->>S: retrieve scoped evidence and draft notice
  S-->>M: return unsent draft for review
  Note over L,S: Missing delay or notification policy remains unknown. Phase 3 sends no message
```

## Stockout risk to pricing consideration

```mermaid
sequenceDiagram
  participant I as Inventory agent
  participant R as Merchant price rule
  participant P as Pricing agent
  participant H as Human approval
  I->>I: forecast coverage from tenant stock and demand
  I->>P: provide scoped stockout risk signal
  P->>R: read explicit stockout markup, floor, ceiling, threshold
  alt markup rule exists
    P->>P: calculate recommendation and approval requirement
  else no markup rule
    P->>P: record risk consideration without inferring a price change
  end
  P-->>H: return proposal with no price write in Phase 3
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
  API->>PG: store source and pending job atomically
  PG->>O: claim job under tenant lock
  O->>PG: parse source and stage deterministic chunks
  O->>Q: idempotent tenant-scoped upsert
  O->>PG: commit chunks and completed receipt
  A->>PG: authorize and resolve tenant scope
  A->>Q: hybrid query with mandatory tenant filter
  Q-->>A: ranked point IDs
  A->>PG: load passages with tenant and customer visibility checks
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

## Signed notifications and replay

```mermaid
sequenceDiagram
  participant P as Provider
  participant A as API
  participant D as Postgres
  participant W as Delivery worker
  participant S as Subscriber
  actor O as Tenant owner
  P->>A: signed event
  A->>A: verify raw bytes and tenant credential
  A->>D: persist minimized idempotent command
  A-->>P: 202 and job ID
  W->>D: claim command and commit domain update with outbound job
  W->>S: signed notification with stable event ID
  alt acknowledged
    W->>D: mark delivered
  else retry limit reached
    W->>D: record dead letter and audit
    O->>A: replay job with idempotency key
    A->>D: requeue original job and audit actor
  end
```
