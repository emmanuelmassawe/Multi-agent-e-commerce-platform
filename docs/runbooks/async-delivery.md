# Operating asynchronous delivery

## Starting a run

Start PostgreSQL, Redis, RabbitMQ, the API, a Celery worker and Beat. Apply Alembic migrations and initialize the Postgres checkpointer with `uv run python scripts/setup_checkpointer.py` before admitting runs. Use your authenticated bearer token for the following requests.

1. Send `POST /v1/runs` with a unique `Idempotency-Key` and a body such as `{"message":"Check inventory stock"}`. Save the `run_id` and `Location` returned with HTTP 202. If the connection breaks, repeat the original request with its original key. Changed input under a used key returns 409.
2. Open `GET /v1/runs/{run_id}/events` with an HTTP streaming client. Persist each SSE `id` after consuming its event. Reconnect with `Last-Event-ID` to continue from the next event. Token usage comes from the model response at each completed call. Heartbeat comments keep idle connections open. The stream closes at completion, failure, budget exhaustion or an approval pause.
3. Open `/v1/approvals/ws` for the tenant's approval events. Native clients can supply the Authorization bearer header and Last-Event-ID. Browser clients send the access token as the first text frame within five seconds and can resume using the `cursor` query parameter. The server emits heartbeat objects during idle periods. Decisions still use the authenticated approvals HTTP endpoint.

Beat dispatches due jobs every two seconds. An accepted command stays in PostgreSQL while the broker or worker is offline. Consumers claim disjoint rows with `FOR UPDATE SKIP LOCKED`. Redis gates run admission, graph nodes, tools and scheduled work. Setting `clos:pause:<tenant UUID>` or `clos:pause:global` to 1 pauses work at the next check. Removing the relevant key resumes processing. Keep these Redis keys under operator access control.

## Signed integration traffic

Provide `INTEGRATIONS` as a secret JSON object keyed by tenant UUID to both API and worker. The default empty object disables integrations. Inject secrets through the environment or secret manager. Reserve distinct signing credentials for each tenant and direction. Shared-secret multi-shop Shopify apps require a separate authenticated shop-to-tenant binding before use.

| Direction | Configuration and authentication | Persisted data |
| --- | --- | --- |
| Shopify order creation | Set `shopify_secret`. Subscribe `orders/create` at `POST /v1/webhooks/{tenant_id}/shopify`. Send `X-Shopify-Topic`, `X-Shopify-Webhook-Id` and `X-Shopify-Hmac-Sha256` (base64 HMAC-SHA256 of the raw body). | Unique order ID, currency and total. Retries with the same order ID share a receipt. |
| Carrier tracking | Set `carrier_secret`. Send `shipment_id`, `status` and timezone-aware `occurred_at` to `POST /v1/webhooks/{tenant_id}/carrier`. Sign the exact request bytes. | Tenant-local shipment event. Late observations preserve the more recent shipment status. |
| Outbound | Supply `outbound_url` and `outbound_secret` together. The worker sends an HTTPS POST with a stable event ID and a fresh signature on every attempt. | Notification carries only the tenant, subject and event identifiers and the event type. |

Carrier and outbound messages use `X-CLOS-Timestamp` (Unix seconds), `X-CLOS-Event-Id` and `X-CLOS-Signature` (hex HMAC-SHA256 over the timestamp, a dot, the event ID, a dot, and the raw body). Verify the signature before parsing, enforce a five-minute clock window and persist the event ID before acknowledging. Outbound subscribers can also deduplicate on the matching `Idempotency-Key`. A receiver that processes a notification and loses the HTTP acknowledgement can receive it again.

## Scheduled observations

Set the following fields in the tenant binding. Each interval is in seconds, with a minimum of 60. Each UTC time slot has a single job for its tenant and category. Missed historical slots are not backfilled. An agent in `off` mode skips the scan. Shadow mode records operational observations. Merchant price proposals and purchase orders follow their existing approval flow.

| Interval | Data source | Result |
| --- | --- | --- |
| `inventory_interval_seconds` | Tenant inventory in PostgreSQL | Audit count of positions whose available quantity is zero or below. |
| `pricing_interval_seconds` | `price_feed_url`, HTTPS JSON array with `listing_id`, `price`, `currency` | Refreshes known competitor listings matching the configured currency. |
| `logistics_interval_seconds` | `tracking_feed_url`, HTTPS JSON array with `shipment_id`, `status`, `occurred_at` | Records known shipments' tracking observations and advances their status by observation time. |

An optional `feed_token` supplies a bearer credential for the two feeds. Feeds must fit within 1 MB. Provide vendor-specific translation at the integration boundary when the vendor's wire format differs from this feed contract.

## Recovering failed work

1. As a tenant owner, call `GET /v1/dead-letters`. The response includes the job ID, kind, attempts and error class. Use the cursor for additional pages.
2. Fix the cause. For example, resolve the missing local shipment or restore the subscribed HTTPS receiver. External destinations enter a short cooldown after repeated failures.
3. Send `POST /v1/dead-letters/{job_id}/replays` with a fresh `Idempotency-Key`. Use the same key when retrying that replay request. A 202 requeues the original job and records the operator in the audit log.
4. Verify completion through run status or the destination's receipt. Scrape `/metrics` for pending and dead job counts. The default attempt limit is five, configurable with `DELIVERY_MAX_ATTEMPTS`. Early attempts back off with jitter.

Authenticated API requests share per-tenant and per-user Redis quotas. Use `RateLimit-Remaining` and `RateLimit-Reset` for pacing. On 429, wait for the seconds in `Retry-After`. A Redis outage returns 503 on protected operations. The local load benchmark uses its own synthetic tenant and elevated quotas in its private API process.
