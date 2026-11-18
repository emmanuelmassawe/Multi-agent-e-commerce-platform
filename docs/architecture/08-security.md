# Trust boundaries and STRIDE threat model

```mermaid
flowchart LR
  subgraph External[Untrusted external boundary]
    User[Merchant / customer]
    Vendors[Stores / carriers / LLM providers]
  end
  subgraph AppBoundary[Authenticated CLOS application boundary]
    Auth[JWT / RBAC / tenant context]
    API[API and request validation]
    Agents[Supervisor and agent tools]
    Guard[Input/output guardrails and PII minimization]
  end
  subgraph DataBoundary[Restricted data boundary]
    PG[(Postgres + RLS + audit + outbox)]
    Q[(Qdrant tenant-filtered index)]
    Redis[(Redis)]
    Sandbox[No-network, resource-limited sandbox]
  end
  User --> Auth --> API --> Agents
  Vendors --> Guard --> Agents
  Agents --> Guard
  Agents --> PG
  Agents --> Q
  Agents --> Redis
  Agents --> Sandbox
```

| STRIDE risk | Phase 0 treatment / required follow-up |
|---|---|
| Spoofing | JWT and RBAC are planned; no authentication exists in Phase 0. |
| Tampering | Input validation and audit records are required in later phases. |
| Repudiation | Append-only audit records are part of the data model plan. |
| Information disclosure | Tenant RLS, PII minimization, and retrieval filters are required before data features. |
| Denial of service | Per-tenant budgets, rate limits, timeouts, and queue controls are later-phase work. |
| Elevation of privilege | Risk-typed tools and approval interrupts are required before writes. |

Treat retrieved documents and all external tool output as untrusted data, never as instructions.

