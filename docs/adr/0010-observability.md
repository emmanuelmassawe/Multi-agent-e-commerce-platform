# 0010. Langfuse, OpenTelemetry, and Prometheus observability

- Status: proposed
- Date: 2026-11-18

## Context

Agent runs need traces and cost visibility; services need standard telemetry and operational metrics.

## Decision drivers

Traceability, PII controls, metric portability, operational burden, and cost.

## Options considered

- Langfuse for agent tracing, OTel instrumentation, Prometheus metrics.
- A single proprietary observability suite.

## Evidence

The prescribed stack names the first option. Costs and comparative performance are not measured yet.

## Decision

Record the prescribed combination as proposed.

## Consequences

PII redaction and metric definitions must be designed before traces or production dashboards are enabled.

