# Customer memory

Start PostgreSQL, RabbitMQ, Redis and Qdrant with Compose, migrate PostgreSQL to head, and start the API, worker and beat services. Beat dispatches work every 15 seconds. A worker processes at most 25 requests for one tenant per delivery. A committed outbox request survives a broker outage. The next dispatch retries it. A failing oldest request blocks later work for that tenant; restore the failed dependency and retry the drain.

## Merchant workflow

Use an owner bearer token or an owner API key scoped to `manage_memory`. Send a fresh `Idempotency-Key` for each mutation and reuse it only for retries of the same input.

1. POST JSON containing `source`, `text` and optionally `customer_id` to `/v1/memory/documents`. Omitting the customer ID shares the document within the tenant. Use shared documents only for merchant-wide policies.
2. Poll `GET /v1/memory/jobs/{run_id}` until completed. A pending receipt means indexing or erasure still needs work.
3. POST `direction` and `text` to `/v1/customers/{customer_id}/memory/messages` to append conversation history. POST a `query` to `/v1/customers/{customer_id}/memory/search` to get an unsent support draft with evidence. The session cache contains a bounded extract of recent messages and expires after 15 minutes. Text processing stays local.
4. GET or DELETE `/v1/customers/{customer_id}/memory` for a private export or erasure. Poll the deletion receipt. Success covers personal memory documents, chunks, conversation messages, scoped Qdrant points and the Redis session. Customer accounts, orders and backup retention have separate lifecycles.

## Recovery

Run the following in the worker environment, replacing TENANT_UUID with an actual tenant UUID. The command runs in the foreground and reports counts of missing, unexpected and changed points before any repair.

```sh
uv run python -m clos.apps.worker.memory drift TENANT_UUID
uv run python -m clos.apps.worker.memory reindex TENANT_UUID
uv run python -m clos.apps.worker.memory drift TENANT_UUID
```

Reindex rebuilds vectors from PostgreSQL and removes index-only points for the requested tenant. If the new encoder requires a different collection layout, configure a new QDRANT_COLLECTION on a maintenance process, rebuild and check each tenant, then switch API and worker configuration together while ingestion is paused. Keep Redis and database credentials in environment settings.
