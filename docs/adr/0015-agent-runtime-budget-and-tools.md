# 0015. Agent runtime budgets and typed tools

- Status: accepted
- Date: 2026-11-18

## Context

Phase 2 needs typed, retryable tool calls and hard per-run limits while the supervisor fans out
independent work. Tool results must remain idempotent across retries, and high-risk writes must not
escape the existing approval policy.

## Decision drivers

Tenant isolation, safety of retries, bounded run cost, testability, and compatibility with LangGraph.

## Options considered

- A Pydantic-validated registry with a durable PostgreSQL idempotency adapter and a fake adapter.
- Direct LangGraph tool nodes with process-local retry and result state.

## Evidence

Unit tests cover schema validation, risk gates, kill-switch behavior, retries, and fake-store
idempotency. A PostgreSQL integration test verifies durable result reuse. A LangGraph eval verifies
multi-agent routing. These checks passed locally on 2026-11-18. Throughput, retry latency, and real
LLM token/cost measurements are not measured yet.

## Decision

Use a typed tool registry and inject a tenant-scoped idempotency port. Production persistence uses a
Postgres transaction advisory lock and `tool_calls` record; tests use a deterministic in-memory fake.
Every write checks autonomy and kill-switch policy. `write_high` requires an explicit approval ID.
Enforce token, step, tool-call, and wall-clock limits with a hard stop.

## Consequences

Tools must pass a stable idempotency key to downstream systems that support it. A worker crash during
an external side effect can cause a retry after the database transaction rolls back, so side-effecting
adapters still need downstream idempotency. Phase 4 will bind approval IDs to persisted approval
records and re-check policy before execution. No real model provider or production token budget was
selected because the owner has not supplied that context.
