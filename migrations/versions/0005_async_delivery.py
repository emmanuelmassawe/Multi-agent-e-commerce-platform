"""Tenant-scoped durable queue and ordered run journal."""
import sqlalchemy as sa
from alembic import op

revision = "0005_async_delivery"
down_revision = "0004_memory_projection"
branch_labels = None
depends_on = None


def common() -> list[sa.Column[object]]:
    return [
        sa.Column("id",sa.Uuid(),primary_key=True),
        sa.Column("tenant_id",sa.Uuid(),sa.ForeignKey("tenants.id",ondelete="CASCADE"),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
    ]


def upgrade() -> None:
    op.create_table("async_jobs",*common(),
        sa.Column("kind",sa.String(32),nullable=False),sa.Column("request_key",sa.String(64),nullable=False),
        sa.Column("fingerprint",sa.String(64),nullable=False),sa.Column("payload",sa.JSON(),nullable=False),
        sa.Column("status",sa.String(16),nullable=False),sa.Column("attempts",sa.Integer(),nullable=False),
        sa.Column("available_at",sa.DateTime(timezone=True),nullable=False),sa.Column("error_code",sa.String(80)),
        sa.UniqueConstraint("tenant_id","kind","request_key",name="uq_async_job_key"))
    op.create_index("ix_async_job_due","async_jobs",["tenant_id","status","available_at"])
    op.create_table("run_events",*common(),sa.Column("run_id",sa.Uuid(),
        sa.ForeignKey("agent_runs.id",ondelete="CASCADE"),nullable=False),
        sa.Column("position",sa.Integer(),nullable=False),sa.Column("event_type",sa.String(40),nullable=False),
        sa.Column("data",sa.JSON(),nullable=False),
        sa.UniqueConstraint("tenant_id","run_id","position",name="uq_run_event_position"))
    check = "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    for table in ("async_jobs","run_events"):
        op.create_index(f"ix_{table}_tenant_id",table,["tenant_id"])
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({check}) WITH CHECK ({check})")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO clos_app")


def downgrade() -> None:
    op.drop_table("run_events")
    op.drop_table("async_jobs")
