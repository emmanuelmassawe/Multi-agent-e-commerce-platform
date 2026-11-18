"""Guarantee one durable tool-call record per tenant run and idempotency key."""

from alembic import op

revision = "0002_tool_call_idempotency"
down_revision = "0001_phase1_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_tool_calls_run_tool_idempotency",
        "tool_calls",
        ["tenant_id", "agent_run_id", "tool_name", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_tool_calls_run_tool_idempotency", "tool_calls", type_="unique")
