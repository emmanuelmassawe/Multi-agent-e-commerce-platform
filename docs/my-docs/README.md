# my-docs — Owner's documentation

Put your own documentation here: business requirements, merchant/customer notes, pricing rules,
carrier and marketplace API docs, meeting notes, diagrams, PDFs, screenshots.

## Rules
- This folder is owned by you. Codex reads it at the start of every phase but never edits, renames or deletes anything here.
- Keep files in Markdown where possible (`.md`) so they are easy for Codex to read. PDFs and images are fine as supporting material.
- Do not store secrets (API keys, passwords) or real customer data here.
- Generated docs (architecture, ADRs, API specs, runbooks, benchmarks) live in the other `docs/` subfolders, not here.

## Suggested structure
```
docs/my-docs/
  requirements/     # what the platform must do, priorities, user stories
  business-rules/   # pricing rules, margins, shipping policies, return policy, approval thresholds
  integrations/     # Shopify, WooCommerce, carriers, WhatsApp, competitor data sources
  data/             # sample data descriptions, field mappings, example CSV/JSON (anonymized)
  meetings/         # notes and decisions
  references/       # papers, links, vendor docs, screenshots
```
