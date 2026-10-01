"""Baseline for the original SQLite/PostgreSQL-compatible schema.

Existing installations are recognized and marked at this baseline; the next
revision then applies the additive lifecycle changes.
"""
from alembic import op
import sqlalchemy as sa

revision="0001_legacy"
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    inspector=sa.inspect(op.get_bind())
    if inspector.has_table("sessions"):
        expected={"sessions","pathways","training_centres","demand_signals","recommendations","handoffs","followups","audit_logs"}
        missing=expected-set(inspector.get_table_names())
        if missing:raise RuntimeError("Existing database is missing legacy tables: "+", ".join(sorted(missing)))
        return
    op.create_table("sessions",
        sa.Column("id",sa.String(),primary_key=True),sa.Column("language",sa.String(),nullable=False),
        sa.Column("state",sa.String(),nullable=False),sa.Column("profile",sa.JSON(),nullable=False),
        sa.Column("consent_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("completed_at",sa.DateTime(timezone=True)))
    op.create_table("pathways",
        sa.Column("id",sa.String(),primary_key=True),sa.Column("title",sa.String(),nullable=False),
        sa.Column("sector",sa.String(),nullable=False),sa.Column("description",sa.Text(),nullable=False),
        sa.Column("skills",sa.JSON(),nullable=False),sa.Column("prerequisites",sa.JSON(),nullable=False),
        sa.Column("min_education",sa.String(),nullable=False),sa.Column("duration_hours",sa.Integer()),
        sa.Column("self_employment",sa.Boolean(),nullable=False),sa.Column("source",sa.String(),nullable=False),
        sa.Column("source_url",sa.String(),nullable=False),sa.Column("active",sa.Boolean(),nullable=False))
    op.create_index("ix_pathways_title","pathways",["title"]);op.create_index("ix_pathways_sector","pathways",["sector"])
    op.create_table("training_centres",
        sa.Column("id",sa.String(),primary_key=True),sa.Column("name",sa.String(),nullable=False),
        sa.Column("district",sa.String(),nullable=False),sa.Column("block",sa.String(),nullable=False),
        sa.Column("latitude",sa.Float(),nullable=False),sa.Column("longitude",sa.Float(),nullable=False),
        sa.Column("address",sa.String(),nullable=False),sa.Column("contact",sa.String(),nullable=False),
        sa.Column("accessibility",sa.String(),nullable=False),sa.Column("source",sa.String(),nullable=False),
        sa.Column("pathway_ids",sa.JSON(),nullable=False))
    op.create_index("ix_training_centres_district","training_centres",["district"])
    op.create_table("demand_signals",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("district",sa.String(),nullable=False),
        sa.Column("sector",sa.String(),nullable=False),sa.Column("demand_label",sa.String(),nullable=False),
        sa.Column("source",sa.String(),nullable=False),sa.Column("year",sa.Integer(),nullable=False),
        sa.Column("capacity",sa.Integer(),nullable=False))
    op.create_index("ix_demand_signals_district","demand_signals",["district"]);op.create_index("ix_demand_signals_sector","demand_signals",["sector"])
    op.create_table("recommendations",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("session_id",sa.String(),sa.ForeignKey("sessions.id"),nullable=False),
        sa.Column("pathway_id",sa.String(),sa.ForeignKey("pathways.id"),nullable=False),sa.Column("selected",sa.Boolean(),nullable=False),
        sa.Column("explanation",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_recommendations_session_id","recommendations",["session_id"])
    op.create_table("handoffs",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("session_id",sa.String(),sa.ForeignKey("sessions.id"),nullable=False),
        sa.Column("reason",sa.String(),nullable=False),sa.Column("priority",sa.String(),nullable=False),
        sa.Column("status",sa.String(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_handoffs_session_id","handoffs",["session_id"])
    op.create_table("followups",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("session_id",sa.String(),sa.ForeignKey("sessions.id"),nullable=False),
        sa.Column("stage",sa.String(),nullable=False),sa.Column("due_date",sa.String(),nullable=False),sa.Column("note",sa.Text(),nullable=False),
        sa.Column("status",sa.String(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
    op.create_index("ix_followups_session_id","followups",["session_id"])
    op.create_table("audit_logs",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("action",sa.String(),nullable=False),
        sa.Column("entity_type",sa.String(),nullable=False),sa.Column("entity_id",sa.String(),nullable=False),
        sa.Column("detail",sa.Text(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))

def downgrade():
    # Baseline is a preservation boundary for installations that may predate Alembic.
    pass
