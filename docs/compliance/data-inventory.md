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
| `approval_requests` | `context`: may contain personal or confidential data; `requested_by`, `decided_by`: staff identifiers; `tool_idempotency_key`: operational idempotency metadata; action/risk/status/expiry: audit data. |
| `tool_calls` | `input_data`, `output_data`: may include personal or confidential data; idempotency key and risk fields: security metadata. |
| `audit_logs` | `actor_id`: staff identifier; `details`: may contain personal/confidential data and must be minimized; action/entity identifiers: security audit data. |
| `token_usage` | model, token counts, cost: operational/cost metadata; run linkage is tenant-restricted. |
| Gemini API request | Supervisor prompt contains the merchant's request; direct email, phone-number, and credential-shaped values are redacted before transmission. It may still contain identifying context that regex redaction does not detect. No customer/order history is attached in Phase 2. Gemini free-tier prompts may be used to improve provider products; customer-confidential content must stay out until legal/privacy review and stronger detection are complete. |

Retention periods, lawful basis, DSAR export/delete behavior, backup deletion, and regional residency are **not specified yet**. Define and enforce them in later phases. This inventory is a draft for legal review, not legal advice.

Phase 4 adds `approval_requests.tool_idempotency_key` as internal operational metadata. The approval
context also stores the proposed tool input, diff, explanation, and decision idempotency key; classify
that context as potentially personal/confidential and minimize it at tool design time.

The owner selected the Gemini free tier as the initial LLM provider. Review Google's current privacy
and data-use terms before sending real merchant/customer data; the phase 2 adapter only redacts
email, phone-number, and credential-shaped strings and is not sufficient for unrestricted PII.

