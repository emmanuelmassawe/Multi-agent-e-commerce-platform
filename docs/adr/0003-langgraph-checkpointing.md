# 0003. LangGraph with Postgres checkpointer

- Status: proposed
- Date: 2026-11-18

## Context

The supervisor needs durable graph state and human approval interrupts with resumable runs. The prescribed stack names LangGraph and a Postgres checkpointer.

## Decision drivers

Durable resume, interrupt support, tenant isolation, operational complexity, and recovery behavior.

## Options considered

- LangGraph with Postgres checkpointer.
- Custom orchestration and checkpoint persistence.

## Evidence

The project instructions prescribe the first option. A crash-recovery spike and timing have not been measured yet.

## Decision

Record LangGraph with Postgres checkpointing as the proposed direction.

## Consequences

Phase 2 must verify checkpointing and crash recovery before claiming it works.

