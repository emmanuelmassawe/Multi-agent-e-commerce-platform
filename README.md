# CLOS

Commerce & Logistics Operating System foundation.

## Local setup

1. Copy `.env.example` to `.env` for local-only development.
2. Run `uv sync --all-groups`.
3. Run `docker compose up --build`.
4. Check `http://localhost:8000/health/live` and `/health/ready`.

Run schema migrations with `uv run alembic upgrade head` using `DATABASE_ADMIN_URL`. The API uses the restricted `DATABASE_URL` role. Set `AUTH_JWT_SECRET` to a random secret before enabling auth routes. Create the initial owner only through `uv run python -m clos.adapters.db.seed` with `SEED_TENANT_SLUG`, `SEED_OWNER_EMAIL`, and `SEED_OWNER_PASSWORD` set in the environment.

See `docs/runbooks/local-database.md` for the local database setup and `CODEX_MASTER_PROMPT.md` for the phased implementation plan.

The [customer memory runbook](docs/runbooks/customer-memory.md) covers uploading policies,
retrieving customer-scoped evidence, erasing private memory, and rebuilding the Qdrant index.

