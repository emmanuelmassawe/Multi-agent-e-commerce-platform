# Initial data inventory and PII classification — needs legal review

This draft classifies the Phase 1 schema. `id`, `tenant_id`, `created_at`, and `updated_at` are present on tenant-owned rows; identifiers and timestamps are operational metadata, but tenant identifiers remain restricted. All tables are tenant-scoped by PostgreSQL RLS except the tenant registry itself. Free-text and JSON payloads are untrusted and must be minimized/redacted before logs, traces, or model calls.

| Table | Columns and classification |
|---|---|
| `tenants` | `id`, `slug`, `name`: merchant operational data; `is_active`, timestamps: operational metadata. Not personal data by default. |
| `users` | `email`, `full_name`: personal data; `password_hash`: credential secret; `role`, `is_active`: access-control data; IDs/timestamps: restricted metadata. |
| `api_keys` | `key_hash`: credential secret; `label`: operator-provided metadata; `permissions`, expiry, last-used, revoked timestamps: security metadata; raw key is returned once and never stored. |
| `refresh_tokens` | `token_hash`: credential secret; expiry/revocation timestamps: security metadata. Raw token is never stored. |
| `products` | `sku`, `name`, `description`, `currency`, `active`: merchant catalog data; `description` must not contain customer personal data. |
| `warehouses` | `name`, `region`, `timezone`: merchant operational data. |
| `suppliers` | `contact_email`: personal data when it identifies a person; `name`, `lead_time_days`: business data. |
| `inventory_items` | product/warehouse IDs and stock quantities: merchant operational data. |
| `customers` | `display_name`, `email`, `phone`: personal data. |
| `orders` | `external_ref`: potentially customer-linked identifier; `customer_id`: linkable personal data; status, currency, total: transaction data. |
| `carriers` | name and supported regions: business integration metadata. |
| `shipments` | `tracking_number`: restricted, potentially customer-linkable identifier; promised date/status: logistics data. |
| `shipment_events` | `payload`: untrusted carrier data that may contain personal data; minimize fields at ingestion. Event type and timestamp: logistics metadata. |
| `price_rules` | product linkage and price/margin limits: merchant-confidential business data. |
| `price_snapshots` | product linkage, price, source, observation time: merchant-confidential pricing data. |
| `competitor_listings` | `external_ref` may identify a public listing; remaining fields are competitive intelligence. |
| `conversations` | `customer_id`: personal-data linkage; status/timestamps: support operations data. |
| `messages` | `body`: likely personal data and customer content; `created_by`: staff identity; minimize and apply retention controls. |
| `agent_runs` | `explanation`: may contain personal or merchant-confidential context; redact before tracing. Agent/status/autonomy fields: operational metadata. |
| `autonomy_settings` | mode and `updated_by`: staff access-control data; tenant-scoped. |
| `approval_requests` | `context`: may contain personal or confidential data; `requested_by`, `decided_by`: staff identifiers; action/risk/status: audit data. |
| `tool_calls` | `input_data`, `output_data`: may include personal or confidential data; idempotency key and risk fields: security metadata. |
| `audit_logs` | `actor_id`: staff identifier; `details`: may contain personal/confidential data and must be minimized; action/entity identifiers: security audit data. |
| `token_usage` | model, token counts, cost: operational/cost metadata; run linkage is tenant-restricted. |

Retention periods, lawful basis, DSAR export/delete behavior, backup deletion, and regional residency are **not specified yet**. Define and enforce them in later phases. This inventory is a draft for legal review, not legal advice.

