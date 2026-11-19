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
  RunIndependentAgents --> ApprovalInterrupt: write_high tool
  ApprovalInterrupt --> PersistApproval
  PersistApproval --> NotifyHuman
  NotifyHuman --> AwaitHuman
  AwaitHuman --> Resume: approved
  AwaitHuman --> Rejected: rejected or expired
  Resume --> RevalidateApproval
  RevalidateApproval --> ExecuteTool: approved input matches and policy allows
  RevalidateApproval --> Rejected: mismatch / kill switch / expired
  ExecuteTool --> Aggregate
  RunIndependentAgents --> Aggregate
  Aggregate --> Respond
  Rejected --> Respond
  Respond --> [*]
  Stopped --> [*]
```

The graph checkpoints each node through LangGraph's PostgreSQL saver.
Checkpoint `thread_id` is derived from the authenticated tenant UUID and run UUID; it is never
accepted from a client. Agent branches are dispatched with LangGraph `Send` and merged before
aggregation. A high-risk tool persists a tenant-scoped approval and audit event before LangGraph
`interrupt`; after resume, the verifier checks the exact approved tool input, tenant, run, tool name,
expiry and current kill-switch context before execution. Approval expiry resumes with rejection.

