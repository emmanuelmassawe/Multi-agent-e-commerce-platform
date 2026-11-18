# 0001. Record project decisions and preserve supplied constraints

- Status: proposed
- Date: 2026-11-18

## Context

The project instructions specify a production platform and a mandatory technology stack. Decisions must be reviewable and evidence-based.

## Decision drivers

Traceability, security, maintainability, reproducible evidence, and honoring product constraints.

## Options considered

- Record decisions as MADR files with a proposed/review/accepted lifecycle.
- Leave decisions only in implementation and inline documentation.

## Evidence

The supplied AGENTS.md and master prompt mandate ADRs. No platform benchmark has been run; performance and costs are not measured yet.

## Decision

Use versioned MADR records and keep the initial stack ADRs proposed until reviewed.

## Consequences

Changes requiring an ADR must wait for review before acceptance. This ADR itself is proposed.

