# 0012. Docker-based sandbox for untrusted execution

- Status: proposed
- Date: 2026-11-18

## Context

Any future code-execution tool must run without network access and with resource limits.

## Decision drivers

Isolation, network egress prevention, resource enforcement, auditability, and operational cost.

## Options considered

- Docker-based local runner; E2B adapter may be evaluated later.
- Execute code in the API or worker process.

## Evidence

The prescribed security rule requires Docker sandboxing. Isolation tests and cost are not measured yet.

## Decision

Record isolated Docker execution as the proposed direction; no code execution is included in Phase 0.

## Consequences

Before enabling a sandbox tool, demonstrate no network access and enforce CPU, memory, time, and filesystem limits.

