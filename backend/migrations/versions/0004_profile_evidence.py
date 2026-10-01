"""Link validated profile values to the interview answer that supplied them."""
from alembic import op
import sqlalchemy as sa

revision="0004_profile_evidence"
down_revision="0003_staff"
branch_labels=None
depends_on=None

def upgrade():
    inspector=sa.inspect(op.get_bind())
    if not inspector.has_table("profile_evidence"):
        op.create_table(
            "profile_evidence",
            sa.Column("id",sa.Integer(),primary_key=True),
            sa.Column("session_id",sa.String(),sa.ForeignKey("sessions.id",ondelete="CASCADE"),nullable=False),
            sa.Column("source_answer_id",sa.Integer(),sa.ForeignKey("interview_answers.id",ondelete="CASCADE"),nullable=False),
            sa.Column("field",sa.String(),nullable=False),
            sa.Column("canonical_value",sa.JSON(),nullable=False),
            sa.Column("confidence",sa.Float(),nullable=False),
            sa.Column("status",sa.String(),nullable=False,server_default="accepted"),
            sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
            sa.UniqueConstraint("session_id","source_answer_id","field",name="uq_profile_evidence_session_answer_field"),
        )
        op.create_index("ix_profile_evidence_session_id","profile_evidence",["session_id"])
        op.create_index("ix_profile_evidence_source_answer_id","profile_evidence",["source_answer_id"])
        op.create_index("ix_profile_evidence_field","profile_evidence",["field"])
    else:
        unique_names={item.get("name") for item in inspector.get_unique_constraints("profile_evidence")}
        if "uq_profile_evidence_answer_field" in unique_names:
            with op.batch_alter_table("profile_evidence",recreate="always") as batch:
                batch.drop_constraint("uq_profile_evidence_answer_field",type_="unique")
                batch.create_unique_constraint("uq_profile_evidence_session_answer_field",["session_id","source_answer_id","field"])

def downgrade():
    op.drop_index("ix_profile_evidence_field",table_name="profile_evidence")
    op.drop_index("ix_profile_evidence_source_answer_id",table_name="profile_evidence")
    op.drop_index("ix_profile_evidence_session_id",table_name="profile_evidence")
    op.drop_table("profile_evidence")
