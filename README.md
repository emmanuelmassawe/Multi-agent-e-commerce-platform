# CLOS

Commerce & Logistics Operating System foundation.

## Local setup

1. Copy `.env.example` to `.env` for local-only development.
2. Run `uv sync --all-groups`.
3. Run `docker compose up --build`.
4. Check `http://localhost:8000/health/live` and `/health/ready`.

The current Phase 0 scaffold does not yet connect health readiness to backing services.
See `CODEX_MASTER_PROMPT.md` for the phased implementation plan.

