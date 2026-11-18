# 0008. Human approval for high-risk actions

- Status: proposed
- Date: 2026-11-18

## Context

High-risk writes such as large price changes, purchase orders, and bulk messaging require explicit human approval.

## Decision drivers

Safety, resumability, auditability, approval expiry, and protection against retry bypass.

## Options considered

- Pause graph execution with LangGraph interrupt and durable ApprovalRequest.
- Permit a tool to execute and notify a human afterward.

## Evidence

The supplied architecture rules require the interrupt path. No HITL behavior is implemented yet.

## Decision

Record the interrupt plus approval request as the proposed control.

## Consequences

No write_high action may execute until the request is explicitly approved; Phase 4 must test bypass paths.

