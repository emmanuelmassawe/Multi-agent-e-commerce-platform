# Initial access-control model

| Role | Initial permissions |
|---|---|
| `owner` | All current permissions; may manage integration API keys. |
| `manager` | Read, catalog/order management, approvals, and integration API keys. |
| `agent-operator` | Read, run agents, and manage approvals. |
| `viewer` | Read only. |

Access JWTs are short-lived. Each request reloads the user inside the tenant scope so deactivation and role changes take effect before authorization. Refresh JWTs are persisted only by hash, locked and revoked when consumed, then rotated. API keys are tenant-prefixed, stored only as a hash, created with a permission subset, and shown to the caller once. Key creation is idempotent for the same tenant, `Idempotency-Key`, and request body; using the same key for a different body returns conflict.

All high-risk agent actions still require the separate approval flow defined by ADR 0008. These Phase 1 identity primitives do not grant a direct bypass around tool-risk checks.

