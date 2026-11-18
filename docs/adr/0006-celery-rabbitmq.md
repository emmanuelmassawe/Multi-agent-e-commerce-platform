# 0006. Celery and RabbitMQ for background work

- Status: accepted
- Date: 2026-11-18

## Context

Long-running runs and scheduled jobs need asynchronous workers, retries, and dead-letter handling.

## Decision drivers

Durable delivery, retry semantics, operational burden, scheduling, and fit with current team skills.

## Options considered

- Celery with RabbitMQ.
- Temporal, which project instructions allow as an alternative after an ADR.

## Evidence

The prescribed default is Celery and RabbitMQ. The worker starts a late-ack Celery consumer and
retries tasks after failures. Worker configuration is unit-tested. Broker throughput and end-to-end
queue recovery measurements are not measured yet.

## Decision

Use Celery with RabbitMQ for worker delivery and retries.

## Consequences

Compose includes RabbitMQ. The worker retries with exponential backoff and jitter and resumes graph
state from PostgreSQL. A dead-letter policy and broker throughput benchmark remain to be configured
and measured before production use.

