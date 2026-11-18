# Local database and identity setup

## Configuration

1. Copy `.env.example` to `.env` and replace every local placeholder. Use a unique random `AUTH_JWT_SECRET` with at least 32 characters.
2. Start PostgreSQL with `docker compose up -d postgres`. The first-run init script creates `clos_app`, a login role without superuser or RLS bypass privileges.
3. The API connects using `DATABASE_URL` as `clos_app`; migrations and controlled seeding use `DATABASE_ADMIN_URL`.
4. Apply or roll back schema with `uv run alembic upgrade head` and `uv run alembic downgrade base`.
5. Initialize LangGraph checkpoint tables as the admin role with `uv run python scripts/setup_checkpointer.py`.
6. Set `SEED_TENANT_SLUG`, `SEED_OWNER_EMAIL`, and `SEED_OWNER_PASSWORD` in the shell, then run `uv run python -m clos.adapters.db.seed`. The seed command requires a password with at least 12 characters and does not print credentials.

## Tenant transactions

Every tenant-owned table has forced row-level security. The API must set `app.current_tenant_id` transaction-locally before reading or writing tenant data. `TenantRepository` additionally filters by tenant ID. Do not connect the API with the PostgreSQL superuser or table owner.

## Tests

Unit tests exercise tenant-scoped repositories with SQLite. PostgreSQL integration tests require migrations and checkpoint setup, with `TEST_DATABASE_URL` and `CHECKPOINT_DATABASE_URL` connecting as the non-superuser app role. CI creates a temporary PostgreSQL service, applies and rolls back migrations, initializes the checkpoint tables, then tests RLS, tool idempotency, and worker recovery.

