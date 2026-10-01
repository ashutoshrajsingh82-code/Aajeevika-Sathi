"""Configurable follow-up states and verified outcome history."""
from alembic import op
import sqlalchemy as sa

revision="0011_followup_outcome_engine"
down_revision="0010_action_plan_counsellor_handoff"
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind();inspector=sa.inspect(bind);tables=set(inspector.get_table_names())
    if "followups" in tables:
        columns={c["name"] for c in inspector.get_columns("followups")}
        additions=[("schedule_offset_days",sa.Integer(),True,None),("rescheduled_from_id",sa.Integer(),True,sa.ForeignKey("followups.id")),("contacted_at",sa.DateTime(timezone=True),True,None),("completed_at",sa.DateTime(timezone=True),True,None),("updated_at",sa.DateTime(timezone=True),True,None)]
        for name,kind,nullable,foreign_key in additions:
            if name not in columns:
                column=sa.Column(name,kind,nullable=nullable,server_default=sa.text("CURRENT_TIMESTAMP") if name=="updated_at" else None)
                if foreign_key is not None:column.append_foreign_key(foreign_key)
                op.add_column("followups",column)
        indexes={x["name"] for x in inspector.get_indexes("followups")}
        if "ix_followups_status" not in indexes:op.create_index("ix_followups_status","followups",["status"])
        bind.execute(sa.text("UPDATE followups SET status=CASE lower(status) WHEN 'pending' THEN 'SCHEDULED' WHEN 'complete' THEN 'COMPLETED' WHEN 'cancelled' THEN 'CANCELLED' ELSE upper(status) END"))
    if "outcomes" not in tables:
        op.create_table("outcomes",
            sa.Column("id",sa.Integer(),primary_key=True),
            sa.Column("session_id",sa.String(),sa.ForeignKey("sessions.id",ondelete="CASCADE"),nullable=False),
            sa.Column("category",sa.String(),nullable=False),
            sa.Column("source",sa.String(),nullable=False),
            sa.Column("reported_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("verification_status",sa.String(),nullable=False,server_default=sa.text("'UNVERIFIED'")),
            sa.Column("verification_note",sa.Text(),nullable=False,server_default=sa.text("''")),
            sa.Column("verified_by",sa.String(),nullable=True),
            sa.Column("verified_at",sa.DateTime(timezone=True),nullable=True),
            sa.Column("note",sa.Text(),nullable=False,server_default=sa.text("''")),
            sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_outcomes_session_id","outcomes",["session_id"])
        op.create_index("ix_outcomes_category","outcomes",["category"])
        op.create_index("ix_outcomes_source","outcomes",["source"])
        op.create_index("ix_outcomes_verification_status","outcomes",["verification_status"])

def downgrade():
    bind=op.get_bind();tables=set(sa.inspect(bind).get_table_names())
    if "outcomes" in tables:op.drop_table("outcomes")
    if "followups" in tables:
        indexes={x["name"] for x in sa.inspect(bind).get_indexes("followups")}
        if "ix_followups_status" in indexes:op.drop_index("ix_followups_status",table_name="followups")
        columns={c["name"] for c in sa.inspect(bind).get_columns("followups")}
        for name in ("updated_at","completed_at","contacted_at","rescheduled_from_id","schedule_offset_days"):
            if name in columns:op.drop_column("followups",name)
