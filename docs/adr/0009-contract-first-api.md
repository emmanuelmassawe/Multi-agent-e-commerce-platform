# 0009. Contract-first versioned API

- Status: proposed
- Date: 2026-11-18

## Context

API consumers need stable schemas, consistent errors, idempotency, pagination, and documented streams.

## Decision drivers

Compatibility, reviewability, code-contract drift detection, and client generation.

## Options considered

- OpenAPI 3.1 source contract with implementation and contract tests.
- Code-first endpoints with documentation generated after implementation.

## Evidence

The supplied API rule prescribes contract-first. Spectral and Schemathesis are not configured yet.

## Decision

Record OpenAPI 3.1 contract-first design under `/v1` as proposed.

## Consequences

The initial file covers health only and must be expanded before further endpoints are implemented.

