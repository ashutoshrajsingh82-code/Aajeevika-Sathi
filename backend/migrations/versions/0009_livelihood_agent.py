"""Persist bounded livelihood agent runs without hidden reasoning traces."""
from alembic import op
import sqlalchemy as sa

revision="0009_livelihood_agent"
down_revision="0008_ocr_provenance"
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind()
    if "livelihood_agent_sessions" in sa.inspect(bind).get_table_names():return
    op.create_table(
        "livelihood_agent_sessions",
        sa.Column("id",sa.String(),primary_key=True),
        sa.Column("beneficiary_session_id",sa.String(),sa.ForeignKey("sessions.id",ondelete="CASCADE"),nullable=False),
        sa.Column("actor_username",sa.String(),nullable=False),
        sa.Column("current_goal",sa.String(),nullable=False),
        sa.Column("tools_used",sa.JSON(),nullable=False),
        sa.Column("tool_results",sa.JSON(),nullable=False),
        sa.Column("final_action",sa.JSON(),nullable=True),
        sa.Column("status",sa.String(),nullable=False,server_default="running"),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
    )
    op.create_index("ix_livelihood_agent_sessions_beneficiary_session_id","livelihood_agent_sessions",["beneficiary_session_id"])
    op.create_index("ix_livelihood_agent_sessions_actor_username","livelihood_agent_sessions",["actor_username"])
    op.create_index("ix_livelihood_agent_sessions_status","livelihood_agent_sessions",["status"])

def downgrade():
    if "livelihood_agent_sessions" in sa.inspect(op.get_bind()).get_table_names():op.drop_table("livelihood_agent_sessions")
