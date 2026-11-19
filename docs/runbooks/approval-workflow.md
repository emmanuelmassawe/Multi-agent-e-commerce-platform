# Human approval workflow

## Enable high-risk approvals

Set `APPROVAL_EXPIRY_SECONDS` to the merchant-approved duration before enabling any write_high
agent tools. The setting has no default because the owner has not supplied an expiry policy. Configure
the API and worker with the same value. Keep the values in environment configuration or a secret
manager, not in this document.

## Operate the inbox

- Authenticated users with `manage_approvals` can list tenant-scoped requests from
  `GET /v1/approvals` and consume audit-backed SSE at `GET /v1/approvals/events`.
- Approve with `POST /v1/approvals/{approval_id}/approve`, reject with
  `POST /v1/approvals/{approval_id}/reject`, or update the validated tool input and approve with
  `PATCH /v1/approvals/{approval_id}`. Supply a unique `Idempotency-Key` on each decision.
- The API records the decision and audit event before enqueueing a tenant/run-scoped graph resume.
  The worker rechecks approval ID, action, tenant, run, status, expiry, and exact approved input
  before any write_high handler executes.
- Celery schedules expiry; overdue pending requests are rejected, audited, and resumed as rejected.
  Listing the inbox also expires due requests as a recovery path.
- Email and WhatsApp delivery have no configured providers or recipients. The dashboard SSE stream is
  the available notification path; provider adapters currently have deterministic fakes for tests.

## Recovery checks

If a decision returns `409`, reload the inbox and inspect the approval status and expiry. If resume
enqueueing fails after the decision is stored, repeat the same decision with the same idempotency key;
the API returns the stored decision and attempts to enqueue resume again. A tool input changed by
modify-and-approve is validated again by the tool registry; invalid input cannot execute.

Do not manually change approval rows or bypass the persisted verifier. For suspected tenant-scope or
approval bypass issues, disable the relevant agent writes and preserve the audit records for review.
