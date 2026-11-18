# 0011. Guardrails behind a replaceable interface

- Status: proposed
- Date: 2026-11-18

## Context

Inputs, outputs, retrieved content, and tool outputs require validation and prompt-injection defenses.

## Decision drivers

Injection resistance, schema validation, latency, false positives, and replaceability.

## Options considered

- NeMo Guardrails or Guardrails AI behind a project port.
- Custom-only validators with no replaceable provider boundary.

## Evidence

The supplied security rule requires an interface and names both options. A comparative evaluation is not measured yet.

## Decision

Record a replaceable guardrails port; defer provider selection pending spike and eval dataset.

## Consequences

This ADR does not authorize one provider. Record evaluation results before accepting the implementation choice.

