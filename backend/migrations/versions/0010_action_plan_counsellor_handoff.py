"""Add structured action plans and assigned counsellor case handoffs."""

from alembic import op
import sqlalchemy as sa


revision = "0010_action_plan_counsellor_handoff"
down_revision = "0009_livelihood_agent"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    # Alembic's default version_num column is VARCHAR(32).
    # This migration revision is longer than 32 characters, so PostgreSQL
    # must allow a larger value before Alembic records revision 0010.
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text(
                """
                ALTER TABLE alembic_version
                ALTER COLUMN version_num TYPE VARCHAR(255)
                """
            )
        )

    inspector = sa.inspect(bind)

    if "beneficiary_cases" in inspector.get_table_names():
        columns = {
            c["name"]
            for c in inspector.get_columns("beneficiary_cases")
        }

        if "structured_action_plan" not in columns:
            op.add_column(
                "beneficiary_cases",
                sa.Column(
                    "structured_action_plan",
                    sa.JSON(),
                    nullable=True,
                ),
            )

    if "handoffs" in inspector.get_table_names():
        columns = {
            c["name"]
            for c in inspector.get_columns("handoffs")
        }

        additions = [
            ("assigned_to", sa.String(), True),
            ("case_state", sa.String(), False),
            ("beneficiary_summary", sa.JSON(), False),
            ("validated_profile", sa.JSON(), False),
            ("recommendations", sa.JSON(), False),
            ("selected_pathway", sa.JSON(), False),
            ("supporting_evidence", sa.JSON(), False),
            ("missing_information", sa.JSON(), False),
            ("eligibility_uncertainty", sa.JSON(), False),
            ("training_options", sa.JSON(), False),
            ("counsellor_questions", sa.JSON(), False),
            ("ai_brief", sa.JSON(), True),
        ]

        for name, typ, nullable in additions:
            default = (
                sa.text("'OPEN'")
                if name == "case_state"
                else sa.text("'[]'")
                if name in {
                    "recommendations",
                    "supporting_evidence",
                    "missing_information",
                    "eligibility_uncertainty",
                    "training_options",
                    "counsellor_questions",
                }
                else sa.text("'{}'")
                if isinstance(typ, sa.JSON) and not nullable
                else None
            )

            if name not in columns:
                op.add_column(
                    "handoffs",
                    sa.Column(
                        name,
                        typ,
                        nullable=nullable,
                        server_default=default,
                    ),
                )

        indexes = {
            x["name"]
            for x in inspector.get_indexes("handoffs")
        }

        if "ix_handoffs_assigned_to" not in indexes:
            op.create_index(
                "ix_handoffs_assigned_to",
                "handoffs",
                ["assigned_to"],
            )

        if "ix_handoffs_case_state" not in indexes:
            op.create_index(
                "ix_handoffs_case_state",
                "handoffs",
                ["case_state"],
            )

        # Preserve legacy records while giving workflow clients
        # a canonical state.
        bind.execute(
            sa.text(
                """
                UPDATE handoffs
                SET case_state =
                    CASE lower(status)
                        WHEN 'accepted' THEN 'ASSIGNED'
                        WHEN 'resolved' THEN 'CLOSED'
                        ELSE 'OPEN'
                    END
                """
            )
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "handoffs" in inspector.get_table_names():
        indexes = {
            x["name"]
            for x in inspector.get_indexes("handoffs")
        }

        for name in (
            "ix_handoffs_assigned_to",
            "ix_handoffs_case_state",
        ):
            if name in indexes:
                op.drop_index(
                    name,
                    table_name="handoffs",
                )

        columns = {
            c["name"]
            for c in inspector.get_columns("handoffs")
        }

        for name in (
            "ai_brief",
            "counsellor_questions",
            "training_options",
            "eligibility_uncertainty",
            "missing_information",
            "supporting_evidence",
            "selected_pathway",
            "recommendations",
            "validated_profile",
            "beneficiary_summary",
            "case_state",
            "assigned_to",
        ):
            if name in columns:
                op.drop_column("handoffs", name)

    if (
        "beneficiary_cases" in inspector.get_table_names()
        and "structured_action_plan"
        in {
            c["name"]
            for c in inspector.get_columns("beneficiary_cases")
        }
    ):
        op.drop_column(
            "beneficiary_cases",
            "structured_action_plan",
        )

