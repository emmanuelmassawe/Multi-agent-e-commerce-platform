# API changelog

## 0.1.0 — 2026-11-18

- Added initial OpenAPI 3.1 health endpoint contract.
- This scaffold is not a complete public API and has no compatibility guarantee yet.
- Added tenant-scoped approval inbox, approve/reject/modify-and-approve actions, and approval SSE events.
- Approval decisions resume the checkpointed graph; high-risk tool input must match the persisted approved input exactly.

## Phase 5

Added owner-scoped plain text ingestion, memory job status, support message append and search, and customer memory export/erasure. Ingestion and erasure return 202 and a durable receipt.

## Phase 6

Added idempotent run admission, status and resumable SSE, a read-only approval WebSocket, signed integration webhook ingestion, tenant-owner dead-letter listing and replay. Protected routes return quota headers. See the [delivery runbook](../runbooks/async-delivery.md).
