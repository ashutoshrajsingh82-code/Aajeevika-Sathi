"""Add recommendation evaluation records."""
from alembic import op
import sqlalchemy as sa

revision="0013_recommendation_evaluations"
down_revision="0012_ai_operation_metrics"
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind()
    if "recommendation_evaluations" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "recommendation_evaluations",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("recommendation_id",sa.Integer(),sa.ForeignKey("recommendations.id",ondelete="CASCADE"),nullable=False),
        sa.Column("session_id",sa.String(),sa.ForeignKey("sessions.id",ondelete="CASCADE"),nullable=False),
        sa.Column("pathway_completed",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("counsellor_corrected",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("pathway_mismatch",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("corrected_pathway_id",sa.String(),sa.ForeignKey("pathways.id"),nullable=True),
        sa.Column("note",sa.Text(),nullable=False,server_default=""),
        sa.Column("evaluator_username",sa.String(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("recommendation_id",name="uq_recommendation_evaluation_recommendation"),
    )
    op.create_index("ix_recommendation_evaluations_recommendation_id","recommendation_evaluations",["recommendation_id"])
    op.create_index("ix_recommendation_evaluations_session_id","recommendation_evaluations",["session_id"])
    op.create_index("ix_recommendation_evaluations_evaluator_username","recommendation_evaluations",["evaluator_username"])

def downgrade():
    op.drop_table("recommendation_evaluations")
