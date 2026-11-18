# API design guidelines

The OpenAPI 3.1 document in `openapi.yaml` is the HTTP contract source of truth. The AsyncAPI document in `asyncapi.yaml` defines SSE, WebSocket, and webhook events. Keep both current before implementing endpoints.

- Use `/v1`, resource nouns, snake_case JSON, UUIDv7 identifiers, and RFC 3339 UTC timestamps.
- Derive tenant scope from authenticated credentials, never from request bodies. Apply RBAC scopes to every protected operation.
- Use cursor pagination (`limit`, `cursor`, `next_cursor`), `filter[field]`, and `sort=-created_at`.
- Return RFC 9457 `application/problem+json` errors with stable `code`, `trace_id`, and field details.
- Mutating calls require `Idempotency-Key`; updates use `ETag` and `If-Match`. Long-running work returns `202`, `run_id`, and `Location`.
- Document rate limits and response headers, auth scopes, schemas/examples, errors, idempotency, and rate-limit class per endpoint.
- Document SSE, WebSocket, and signed/retried webhooks in AsyncAPI. Breaking changes require a new API version and ADR; use `Deprecation` and `Sunset` headers.

Contract linting and Schemathesis contract tests are planned CI gates. The Phase 0 API is a starter contract and is not yet a complete product API.

