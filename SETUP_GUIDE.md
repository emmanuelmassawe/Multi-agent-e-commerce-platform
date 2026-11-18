# Setup guide — from zero to Phase 0

## 1. Prerequisites on your computer
- VS Code with the Codex extension installed and signed in
- Git
- Docker Desktop (or Docker Engine + Compose)
- Python 3.12 and `uv`
- Node.js LTS (needed from Phase 9)
- Later (Phase 11): Terraform, AWS CLI, an AWS account. Not needed for Phases 0-10.

## 2. Create the project
1. Unzip `clos-starter.zip` into a new folder named `clos`.
2. In a terminal: `cd clos && git init && git add . && git commit -m "chore: starter files"`
3. Open the folder in VS Code.

## 3. Fill in your documentation (most important step)
Open `docs/my-docs/` and fill in the templates:
- `requirements/REQUIREMENTS_TEMPLATE.md` (copy to `requirements/main.md`)
- `business-rules/BUSINESS_RULES_TEMPLATE.md` (copy to `business-rules/main.md`)
Add anything else you have: carrier docs, Shopify/WooCommerce notes, meeting notes, screenshots.
Never put real API keys or real customer data there.

## 4. Start Codex
1. Open Codex in VS Code in the `clos` folder.
2. Paste the prompt from `CODEX_KICKOFF.md`.
3. Answer Codex's questions. Then it executes Phase 0 only.

## 5. Loop for every phase
1. Read Codex's phase report. Do not trust it blindly: run `git diff`, run the tests yourself.
2. Use a review prompt from `PHASE_PROMPTS.md` (honesty, security, architecture).
3. Commit/merge the phase on its own branch (`phase-0`, `phase-1`, ...).
4. Paste the next phase prompt.

## 6. Things you must decide early (put answers in docs/my-docs/)
- Target markets/countries and languages
- E-commerce platforms to integrate first (Shopify, WooCommerce, custom)
- Carriers and payment methods in your market
- Which LLM provider(s) you want and your monthly budget
- Approval thresholds (e.g. price change above X%, reorder above Y amount)

## 7. Cautions
- Codex outputs can contain mistakes. Review security-sensitive code (auth, tenant isolation, HITL) yourself.
- Do not run `terraform apply` on a real AWS account until you reviewed the plan and costs.
- Benchmarks in docs must come from real runs. If you see numbers without a command and date, challenge them.
