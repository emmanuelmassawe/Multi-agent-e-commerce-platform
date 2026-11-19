# 0008. Human approval for high-risk actions

- Status: accepted
- Date: 2026-11-19

## Context

High-risk writes such as price changes above configured limits, purchase orders, and bulk messaging
must wait for an authorized human decision. The database already contains tenant-scoped approval,
run, tool-call, and audit records. Phase 4 must make those records drive graph execution.

## Decision drivers

Safety, resumability, auditability, approval expiry, and protection against retry bypass.

## Options considered

- Pause graph execution with LangGraph interrupt and durable ApprovalRequest.
- Permit a tool to execute and notify a human afterward.

## Evidence

Unit and LangGraph in-memory checkpoint tests verify that a write_high handler does not execute before
an interrupt, rejects a rejected decision, validates a modified input against its Pydantic schema,
and executes only after the persisted verifier accepts the exact approved input. PostgreSQL
integration tests passed on 2026-11-19 for tenant scoping, idempotent request creation, modified
approval input, exact-input verification, expiry, and audit recording. The crash-recovery test also
passed after the PostgreSQL checkpointer schema was initialized. Notification provider delivery and
production resume latency are not measured yet.

## Decision

Before a write_high handler can run, create a tenant/run/tool-scoped approval request with exact tool
input, proposed diff, explanation, and explicit expiry; append an audit record; notify through the
dashboard approval event stream; then call LangGraph `interrupt`. Resume only when the approval ID,
tenant, run, tool, expiry, persisted decision, and exact approved input all match. Modify-and-approve
stores the new validated input and diff. Rejection and expiry resume without executing the write.
Approval decisions require the `manage_approvals` permission and an idempotency key. Expiry has no
product default and must be configured with `APPROVAL_EXPIRY_SECONDS`.

## Consequences

No write_high action may execute until the request is explicitly approved and revalidated after graph
resume. PostgreSQL unique constraints deduplicate approval creation across worker retries. The
dashboard SSE stream reads tenant-scoped audit events; email and WhatsApp remain ports with fakes
until the owner selects providers. Celery schedules expiry and run resume. The local implementation
must remain fail-closed if its approval configuration or verifier is absent.

