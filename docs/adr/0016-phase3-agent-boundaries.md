# 0016. Phase 3 agent boundaries and tenant-scoped ports

- Status: accepted
- Date: 2026-11-18

## Context

Phase 3 adds four agents before commerce, competitor, carrier, or vector providers are selected and
before the owner has supplied business thresholds. Agent code must work with fakes without allowing
missing provider or merchant policy choices to leak into business logic.

## Decision drivers

Tenant/customer isolation, deterministic tests, no invented business rules, replaceable external
providers, and safe handling of writes.

## Options considered

- Put integrations and policy defaults directly in each agent.
- Define ports, provide deterministic fakes, and pass explicit rules/context into calculations.

## Evidence

Phase 3 deterministic checks exercise tenant-separated stock, tenant/customer-separated support
retrieval, explicit pricing floors and stockout markup, missing logistics policy, and proposal-only
writes. Real integrations, latency, and business outcomes are not measured yet.

## Decision

Agent operations depend on typed ports and receive tenant/run scope from trusted execution context.
Support retrieval additionally requires customer scope. Business thresholds are explicit inputs. When
policy is absent, agents describe uncertainty and produce drafts/proposals; they do not invent rules.
External writes remain behind the existing tool risk and approval policy. Production integrations
must supply tenant-filtered adapters and idempotent downstream operations.

## Consequences

Provider adapters and Phase 4 graph interrupt/resume remain follow-up work. Current fake-backed tools
demonstrate contracts but do not establish production integration behavior. Deployments must
configure real runners and scoped adapters.
