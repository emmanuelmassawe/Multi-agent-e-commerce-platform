# API changelog

## 0.1.0 — 2026-11-18

- Added initial OpenAPI 3.1 health endpoint contract.
- This scaffold is not a complete public API and has no compatibility guarantee yet.
- Added tenant-scoped approval inbox, approve/reject/modify-and-approve actions, and approval SSE events.
- Approval decisions resume the checkpointed graph; high-risk tool input must match the persisted approved input exactly.

