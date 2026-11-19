# Agent component diagrams

```mermaid
flowchart LR
  subgraph Inventory[Inventory agent]
    IGraph[Inventory runner] --> ITools[Typed stock / forecast / reorder operations]
    IGraph --> IPolicy[Reorder policy]
    IGraph --> IPrompt[Versioned prompt]
    IGraph --> IGuard[Input and output guardrails]
  end
  subgraph Pricing[Pricing agent]
    PGraph[Pricing runner] --> PTools[Competitor / recommendation / price operations]
    PGraph --> PPolicy[Margin and price rules]
    PGraph --> PPrompt[Versioned prompt]
    PGraph --> PGuard[Input and output guardrails]
  end
  subgraph Logistics[Logistics agent]
    LGraph[Logistics runner] --> LTools[Tracking / delay / route operations]
    LGraph --> LPolicy[Carrier and service policy]
    LGraph --> LPrompt[Versioned prompt]
    LGraph --> LGuard[Input and output guardrails]
  end
  subgraph Support[Customer support agent]
    SGraph[Support agent] --> STools[Draft answer / report / escalate operations]
    SGraph --> SRAG[Tenant-scoped RAG port]
    SGraph --> SPrompt[Versioned prompt]
    SGraph --> SGuard[PII and injection guardrails]
  end
  Tools[Typed tools with Pydantic validation, risk and idempotency]
  Memory[Retrieval port: tenant + customer scoped]
  ITools --> Tools
  PTools --> Tools
  LTools --> Tools
  STools --> Tools
  SRAG --> Memory
  Memory --> Qdrant[Scoped hybrid ranking]
  Memory --> SQL[Authorized source text]
```

Phase 3 implements deterministic agent services behind replaceable ports and fake integrations.
Inventory, pricing, and logistics proposals do not execute external writes. Support retrieval requires
both tenant and customer scope and produces drafts only. Merchant thresholds and provider selections
remain explicit inputs until supplied.

## Phase 2 runtime

```mermaid
flowchart LR
  Request[Untrusted merchant request] --> Supervisor[LangGraph supervisor]
  Supervisor --> Classify[Versioned intent prompt + LLMPort]
  Classify -->|independent routes| Inventory[Injected inventory runner]
  Classify -->|independent routes| Pricing[Injected pricing runner]
  Classify -->|independent routes| Logistics[Injected logistics runner]
  Classify -->|independent routes| Support[Injected support runner]
  Inventory --> Merge[Aggregate response]
  Pricing --> Merge
  Logistics --> Merge
  Support --> Merge
  Supervisor --> Budget[Hard run budgets]
  Supervisor --> Checkpoints[Postgres checkpointer: tenant/run thread]
  Tools --> Registry[Typed registry + Pydantic + policy checks]
  Registry --> ToolCallTable[ToolCall idempotency record]
```

The dispatcher invokes configured tenant-scoped runners and aggregates their summaries. If a runner
is not configured, it reports that fact rather than claiming the agent completed work. Phase 4 adds
graph interrupts and approval resume before high-risk writes.

