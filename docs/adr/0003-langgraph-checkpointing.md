# 0003. LangGraph with Postgres checkpointer

- Status: accepted
- Date: 2026-11-18

## Context

The supervisor needs durable graph state and human approval interrupts with resumable runs. The prescribed stack names LangGraph and a Postgres checkpointer.

## Decision drivers

Durable resume, interrupt support, tenant isolation, operational complexity, and recovery behavior.

## Options considered

- LangGraph with Postgres checkpointer.
- Custom orchestration and checkpoint persistence.

## Evidence

The project instructions prescribe the first option. A deterministic recovery test interrupts after
classification, closes its PostgreSQL saver, then resumes through a newly constructed graph and
saver on PostgreSQL 16. The integration check passed locally on 2026-11-18; latency and process-level
worker-kill recovery time are not measured yet. Reproduce with
`CHECKPOINT_DATABASE_URL=postgresql+asyncpg://clos_app:local-only-change-me@localhost:5432/clos` and
`uv run pytest tests/integration/test_checkpoint_resume.py -q`.

## Decision

Use LangGraph with the PostgreSQL checkpointer. Checkpoint threads are namespaced by tenant UUID
and run UUID, and the runtime derives these IDs rather than accepting them from callers.

## Consequences

The checkpoint schema is initialized as part of database setup. Resume behavior is verified; a worker
process kill drill and recovery timing remain unmeasured.

