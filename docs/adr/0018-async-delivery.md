# 0018. Asynchronous runs and integration delivery

## Status
Proposed for Phase 6.

## Context and decision drivers
A broker outage between a database commit and publish must not lose an accepted request. Clients reconnect to streams and providers redeliver notifications. Only credentials or per-tenant integration secrets establish scope.

## Options considered
Publishing directly after commit leaves a loss window. Broker-only retry queues do not provide a tenant-scoped replay receipt. A PostgreSQL outbox with Celery consumers fits the existing stack and RLS policies.

## Decision
Persist each command with an idempotency fingerprint in the same transaction as its run or inbound receipt. Beat dispatches due work through RabbitMQ. Consumers acquire a row lock with SKIP LOCKED, bound retries and park exhausted work in a PostgreSQL dead-letter queue. Owner replay reuses the same identity and is audited. External delivery is at least once. Subscribers deduplicate the signed event ID. Keep a sequenced run journal and use Last-Event-ID for SSE. Authenticate live approval sockets using bearer credentials. Polling, limits and integration enablement are configurable.

## Consequences
A worker uses one transaction while processing a job. Bound the operation time and cap delivery batches. Recovery resumes from LangGraph checkpoints. No arbitrary destination URL is accepted from API callers.
