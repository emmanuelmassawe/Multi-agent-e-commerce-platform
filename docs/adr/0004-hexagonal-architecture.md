# 0004. Hexagonal architecture boundaries

- Status: proposed
- Date: 2026-11-18

## Context

The domain must remain independent of frameworks and external systems must be replaceable behind ports.

## Decision drivers

Testability, dependency direction, provider replacement, and isolation of business policy.

## Options considered

- Domain/application/adapters with ports and adapters.
- Framework-centered modules with direct infrastructure calls.

## Evidence

The supplied architecture rules prescribe clean boundaries. Comparative measurements are not measured yet.

## Decision

Use domain <- application <- adapters dependency direction, pending review.

## Consequences

Future code must keep framework imports outside the pure domain layer.

