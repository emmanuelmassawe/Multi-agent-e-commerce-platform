# 0006. Celery and RabbitMQ for background work

- Status: proposed
- Date: 2026-11-18

## Context

Long-running runs and scheduled jobs need asynchronous workers, retries, and dead-letter handling.

## Decision drivers

Durable delivery, retry semantics, operational burden, scheduling, and fit with current team skills.

## Options considered

- Celery with RabbitMQ.
- Temporal, which project instructions allow as an alternative after an ADR.

## Evidence

The prescribed default is Celery and RabbitMQ. Throughput and recovery comparisons are not measured yet.

## Decision

Record Celery and RabbitMQ as proposed pending an implementation spike.

## Consequences

Compose includes RabbitMQ. Production adoption requires retry, DLQ, idempotency, and recovery validation.

