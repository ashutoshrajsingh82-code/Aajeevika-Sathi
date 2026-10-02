"""Persist privacy-safe AI operation metrics."""
from alembic import op
import sqlalchemy as sa

revision="0012_ai_operation_metrics"
down_revision="0011_followup_outcome_engine"
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind()
    if "ai_operation_metrics" in sa.inspect(bind).get_table_names(): return
    op.create_table(
        "ai_operation_metrics",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("request_id",sa.String(),nullable=False),
        sa.Column("session_id",sa.String(),nullable=True),
        sa.Column("operation",sa.String(),nullable=False),
        sa.Column("model",sa.String(),nullable=False,server_default=sa.text("'disabled'")),
        sa.Column("event_kind",sa.String(),nullable=False,server_default=sa.text("'operation'")),
        sa.Column("latency_ms",sa.Float(),nullable=False),
        sa.Column("outcome",sa.String(),nullable=False),
        sa.Column("validation_failure",sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column("prompt_tokens",sa.Integer(),nullable=True),
        sa.Column("completion_tokens",sa.Integer(),nullable=True),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_ai_operation_metrics_request_id","ai_operation_metrics",["request_id"])
    op.create_index("ix_ai_operation_metrics_session_id","ai_operation_metrics",["session_id"])
    op.create_index("ix_ai_operation_metrics_operation","ai_operation_metrics",["operation"])
    op.create_index("ix_ai_operation_metrics_event_kind","ai_operation_metrics",["event_kind"])
    op.create_index("ix_ai_operation_metrics_outcome","ai_operation_metrics",["outcome"])
    op.create_index("ix_ai_operation_metrics_created_at","ai_operation_metrics",["created_at"])

def downgrade():
    op.drop_table("ai_operation_metrics")
