"""Add counsellor and outcome workflow evaluation records."""
from alembic import op
import sqlalchemy as sa

revision = "0016_counsellor_outcome_evaluations"
down_revision = "0015_agent_evaluations"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if "counsellor_outcome_evaluations" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "counsellor_outcome_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("expected_behavior", sa.String(), nullable=False),
        sa.Column("handoff_reviewed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("followup_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("outcome_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence_sufficient", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("correction_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("safe_outcome", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evaluator_username", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_counsellor_outcome_evaluations_category", "counsellor_outcome_evaluations", ["category"])
    op.create_index("ix_counsellor_outcome_evaluations_evaluator_username", "counsellor_outcome_evaluations", ["evaluator_username"])


def downgrade():
    op.drop_table("counsellor_outcome_evaluations")
