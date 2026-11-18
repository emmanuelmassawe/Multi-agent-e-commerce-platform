# Initial ERD direction

The entities below are planning-level only; Phase 1 defines the schema and every tenant-owned table must include `tenant_id` and RLS policy.

```mermaid
erDiagram
  TENANT ||--o{ USER : contains
  TENANT ||--o{ PRODUCT : owns
  TENANT ||--o{ INVENTORY_ITEM : owns
  TENANT ||--o{ ORDER : owns
  TENANT ||--o{ SHIPMENT : owns
  TENANT ||--o{ CUSTOMER : owns
  TENANT ||--o{ CONVERSATION : owns
  TENANT ||--o{ AGENT_RUN : owns
  TENANT ||--o{ APPROVAL_REQUEST : owns
  TENANT ||--o{ AUDIT_LOG : owns
  ORDER ||--o{ SHIPMENT : fulfills
  CUSTOMER ||--o{ CONVERSATION : starts
  CONVERSATION ||--o{ MESSAGE : contains
  AGENT_RUN ||--o{ TOOL_CALL : invokes
  AGENT_RUN ||--o{ TOKEN_USAGE : records
  AGENT_RUN ||--o{ APPROVAL_REQUEST : pauses_for
  TENANT { uuid id PK }
  USER { uuid id PK; uuid tenant_id FK }
  PRODUCT { uuid id PK; uuid tenant_id FK }
  INVENTORY_ITEM { uuid id PK; uuid tenant_id FK }
  ORDER { uuid id PK; uuid tenant_id FK }
  SHIPMENT { uuid id PK; uuid tenant_id FK }
  CUSTOMER { uuid id PK; uuid tenant_id FK }
  CONVERSATION { uuid id PK; uuid tenant_id FK }
  MESSAGE { uuid id PK; uuid tenant_id FK }
  AGENT_RUN { uuid id PK; uuid tenant_id FK }
  TOOL_CALL { uuid id PK; uuid tenant_id FK }
  APPROVAL_REQUEST { uuid id PK; uuid tenant_id FK }
  AUDIT_LOG { uuid id PK; uuid tenant_id FK }
  TOKEN_USAGE { uuid id PK; uuid tenant_id FK }
```

