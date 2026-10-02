"""Add reviewed RAG evaluation records."""
from alembic import op
import sqlalchemy as sa

revision = "0014_rag_evaluations"
down_revision = "0013_recommendation_evaluations"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if "rag_evaluations" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "rag_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("expected_behavior", sa.String(), nullable=False),
        sa.Column("retrieved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retrieval_success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("answer_supported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("unknown_handled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("outdated_document_detected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evaluator_username", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_rag_evaluations_category", "rag_evaluations", ["category"])
    op.create_index("ix_rag_evaluations_evaluator_username", "rag_evaluations", ["evaluator_username"])

def downgrade():
    op.drop_table("rag_evaluations")
