"""One-time generator for the frozen Phase 1 PostgreSQL schema revision."""

from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from clos.adapters.db.models import Base, TENANT_TABLE_NAMES


target = Path("migrations/versions/0001_phase1_core.py")
if target.exists():
    raise SystemExit(f"Refusing to overwrite existing revision: {target}")

dialect = postgresql.dialect()
statements: list[str] = []
for table in Base.metadata.sorted_tables:
    statements.append(str(CreateTable(table).compile(dialect=dialect)).strip())
    statements.extend(
        str(CreateIndex(index).compile(dialect=dialect)).strip()
        for index in sorted(table.indexes, key=lambda item: item.name or "")
    )

table_names = tuple(table.name for table in Base.metadata.sorted_tables)
sql_lines = "\n".join(f"    {statement!r}," for statement in statements)
source = f'''"""Frozen PostgreSQL schema for the Phase 1 core model."""

from alembic import op

revision = "0001_phase1_core"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = {TENANT_TABLE_NAMES!r}
DOWNGRADE_TABLES = {tuple(reversed(table_names))!r}
UPGRADE_SQL = (
{sql_lines}
)


def upgrade() -> None:
    for statement in UPGRADE_SQL:
        op.execute(statement)
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{{table}}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{{table}}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f"CREATE POLICY tenant_isolation ON \\\"{{table}}\\\" "
            "USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)"
        )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO clos_app"
    )


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{{table}}"')
    for table in DOWNGRADE_TABLES:
        op.execute(f'DROP TABLE "{{table}}"')
'''
target.write_text(source, encoding="utf-8")
print(f"Wrote frozen schema revision {target} with {len(statements)} DDL statements")

