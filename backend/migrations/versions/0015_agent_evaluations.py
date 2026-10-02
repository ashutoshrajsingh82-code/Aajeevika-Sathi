"""Add reviewed livelihood agent evaluation records."""
from alembic import op
import sqlalchemy as sa

revision = "0015_agent_evaluations"
down_revision = "0014_rag_evaluations"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "agent_evaluations" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "agent_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scenario", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("expected_behavior", sa.String(), nullable=False),
        sa.Column("tool_allowlist_enforced", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("authorization_enforced", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("missing_data_handled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("escalation_triggered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("loop_prevented", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("safe_outcome", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evaluator_username", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_agent_evaluations_category", "agent_evaluations", ["category"])
    op.create_index("ix_agent_evaluations_evaluator_username", "agent_evaluations", ["evaluator_username"])


def downgrade():
    op.drop_table("agent_evaluations")
