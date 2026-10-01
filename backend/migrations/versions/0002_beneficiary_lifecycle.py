"""Add durable interview evidence and beneficiary cases without deleting data."""
from alembic import op
import sqlalchemy as sa

revision="0002_lifecycle"
down_revision="0001_legacy"
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind();inspector=sa.inspect(bind)
    session_columns={c["name"] for c in inspector.get_columns("sessions")}
    for name,column in (
        ("last_activity_at",sa.Column("last_activity_at",sa.DateTime(timezone=True),nullable=True)),
        ("completion_percentage",sa.Column("completion_percentage",sa.Integer(),nullable=False,server_default="0")),
        ("interview_version",sa.Column("interview_version",sa.String(),nullable=False,server_default="1")),
    ):
        if name not in session_columns:op.add_column("sessions",column)
    existing=set(sa.inspect(bind).get_table_names())
    if "interview_answers" not in existing:
        op.create_table("interview_answers",
            sa.Column("id",sa.Integer(),primary_key=True),
            sa.Column("session_id",sa.String(),sa.ForeignKey("sessions.id",ondelete="CASCADE"),nullable=False),
            sa.Column("slot",sa.String(),nullable=False),sa.Column("question",sa.Text(),nullable=False),
            sa.Column("answer",sa.Text(),nullable=False),sa.Column("normalized_answer",sa.JSON(),nullable=False),
            sa.Column("input_method",sa.String(),nullable=False),sa.Column("language",sa.String(),nullable=False),
            sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    if not sa.inspect(bind).has_index("interview_answers","ix_interview_answers_session_id"):
        op.create_index("ix_interview_answers_session_id","interview_answers",["session_id"])
    if "beneficiary_cases" not in existing:
        op.create_table("beneficiary_cases",
            sa.Column("id",sa.Integer(),primary_key=True),
            sa.Column("session_id",sa.String(),sa.ForeignKey("sessions.id",ondelete="CASCADE"),nullable=False),
            sa.Column("status",sa.String(),nullable=False),
            sa.Column("selected_pathway_id",sa.String(),sa.ForeignKey("pathways.id"),nullable=True),
            sa.Column("action_plan",sa.JSON(),nullable=False),sa.Column("outcome",sa.String(),nullable=False),
            sa.Column("outcome_note",sa.Text(),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
    if not sa.inspect(bind).has_index("beneficiary_cases","ix_beneficiary_cases_session_id"):
        op.create_index("ix_beneficiary_cases_session_id","beneficiary_cases",["session_id"],unique=True)

def downgrade():
    op.drop_index("ix_beneficiary_cases_session_id",table_name="beneficiary_cases")
    op.drop_table("beneficiary_cases")
    op.drop_index("ix_interview_answers_session_id",table_name="interview_answers")
    op.drop_table("interview_answers")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_column("interview_version");batch.drop_column("completion_percentage");batch.drop_column("last_activity_at")
