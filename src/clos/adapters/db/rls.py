"""PostgreSQL row-level security policy helpers."""

from sqlalchemy import Connection, text

from clos.adapters.db.models import TENANT_TABLE_NAMES


def create_tenant_rls_policies(connection: Connection) -> None:
    """Enable and force the tenant policy on every tenant-owned table."""
    for table_name in TENANT_TABLE_NAMES:
        connection.execute(text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
        connection.execute(text(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY'))
        connection.execute(
            text(
                f'''CREATE POLICY "tenant_isolation" ON "{table_name}"
                USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)'''
            )
        )
    connection.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO clos_app"))


def drop_tenant_rls_policies(connection: Connection) -> None:
    """Remove tenant RLS policies during a downgrade."""
    for table_name in TENANT_TABLE_NAMES:
        connection.execute(text(f'DROP POLICY IF EXISTS "tenant_isolation" ON "{table_name}"'))

