"""Durable document sources, chunks and scoped outbox receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0004_memory_projection"
down_revision = "0003_approval_idempotency"
branch_labels = None
depends_on = None

TABLES = ("memory_documents", "memory_chunks", "memory_jobs")


def common() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        TABLES[0],
        *common(),
        sa.Column("customer_id", sa.Uuid(), sa.ForeignKey("customers.id")),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
    )
    op.create_table(
        TABLES[1],
        *common(),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("memory_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
    )
    op.create_index("ix_memory_chunks_document_id", TABLES[1], ["document_id"])
    op.create_table(
        TABLES[2],
        *common(),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("subject_id", sa.Uuid()),
        sa.Column("fingerprint", sa.String(64)),
        sa.Column("status", sa.String(16), nullable=False),
    )
    scope = "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    for table in TABLES:
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING ({scope}) WITH CHECK ({scope})"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO clos_app")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
