# Supervisor LangGraph state diagram

```mermaid
stateDiagram-v2
  [*] --> ValidateInput
  ValidateInput --> BudgetCheck
  BudgetCheck --> ClassifyIntent
  BudgetCheck --> Stopped: budget exceeded / kill switch
  ClassifyIntent --> RouteAgents
  RouteAgents --> RunIndependentAgents: parallel independent branches
  RunIndependentAgents --> Aggregate
  Aggregate --> ApprovalInterrupt: write_high proposal
  ApprovalInterrupt --> AwaitHuman
  AwaitHuman --> Resume: approved
  AwaitHuman --> Rejected: rejected or expired
  Resume --> BudgetCheck
  RunIndependentAgents --> Aggregate
  Aggregate --> Respond
  Rejected --> Respond
  Respond --> [*]
  Stopped --> [*]
```

The implemented Phase 2 graph checkpoints each node through LangGraph's PostgreSQL saver.
Checkpoint `thread_id` is derived from the authenticated tenant UUID and run UUID; it is never
accepted from a client. Agent branches are dispatched with LangGraph `Send` and merged before
aggregation. The initial branch nodes only confirm routing; business tools arrive in Phase 3.

