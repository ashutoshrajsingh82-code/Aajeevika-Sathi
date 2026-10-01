"""Persist transparent scoring components and source details for each recommendation."""
from alembic import op
import sqlalchemy as sa

revision="0005_recommendation_details"
down_revision="0004_profile_evidence"
branch_labels=None
depends_on=None

def upgrade():
    columns={item["name"] for item in sa.inspect(op.get_bind()).get_columns("recommendations")}
    for name,column in (
        ("score",sa.Column("score",sa.Float(),nullable=True)),
        ("component_scores",sa.Column("component_scores",sa.JSON(),nullable=True)),
        ("matched_skills",sa.Column("matched_skills",sa.JSON(),nullable=True)),
        ("missing_skills",sa.Column("missing_skills",sa.JSON(),nullable=True)),
        ("demand_signal",sa.Column("demand_signal",sa.JSON(),nullable=True)),
        ("feasibility",sa.Column("feasibility",sa.JSON(),nullable=True)),
        ("data_sources",sa.Column("data_sources",sa.JSON(),nullable=True)),
        ("model_version",sa.Column("model_version",sa.String(),nullable=True)),
    ):
        if name not in columns:op.add_column("recommendations",column)

def downgrade():
    with op.batch_alter_table("recommendations") as batch:
        for name in ("model_version","data_sources","feasibility","demand_signal","missing_skills","matched_skills","component_scores","score"):
            batch.drop_column(name)
