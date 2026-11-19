"""Add idempotent approval request identity for resumable tool interrupts."""

import sqlalchemy as sa
from alembic import op

revision = "0003_approval_idempotency"
down_revision = "0002_tool_call_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "approval_requests",
        sa.Column("tool_idempotency_key", sa.String(length=200), nullable=True),
    )
    op.create_unique_constraint(
        "uq_approvals_run_action_idempotency",
        "approval_requests",
        ["tenant_id", "agent_run_id", "action", "tool_idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_approvals_run_action_idempotency", "approval_requests", type_="unique")
    op.drop_column("approval_requests", "tool_idempotency_key")
