# 0013. LLM provider port with fallback

- Status: proposed
- Date: 2026-11-18

## Context

Agent models may need to change by tenant, region, capability, or availability.

## Decision drivers

Provider portability, fallback behavior, PII controls, latency, and per-tenant cost limits.

## Options considered

- Provider-neutral LLMPort with primary and fallback model adapters.
- Direct vendor SDK calls throughout agent implementations.

## Evidence

The supplied rule prescribes a provider abstraction and fallback. Provider quality and cost are not measured yet.

## Decision

Record LLMPort and fallback support as proposed.

## Consequences

Provider selection, regional constraints, and real-model benchmarks remain open and require product input and ADR review.

