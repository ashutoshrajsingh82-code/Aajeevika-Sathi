"""Add source documents and portable vector chunks for grounded retrieval."""
from alembic import op
import sqlalchemy as sa

revision="0006_knowledge_rag"
down_revision="0005_recommendation_details"
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind();tables=set(sa.inspect(bind).get_table_names())
    if "knowledge_documents" not in tables:
        op.create_table("knowledge_documents",
            sa.Column("id",sa.String(),primary_key=True),sa.Column("title",sa.String(),nullable=False),sa.Column("source",sa.String(),nullable=False),
            sa.Column("authority",sa.String(),nullable=False),sa.Column("category",sa.String(),nullable=False),sa.Column("district",sa.String(),nullable=True),
            sa.Column("state",sa.String(),nullable=True),sa.Column("effective_date",sa.String(),nullable=True),sa.Column("last_verified",sa.String(),nullable=True),
            sa.Column("version",sa.String(),nullable=False),sa.Column("status",sa.String(),nullable=False),sa.Column("content_hash",sa.String(),nullable=False),
            sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
        for name,column in (("ix_knowledge_documents_title","title"),("ix_knowledge_documents_category","category"),("ix_knowledge_documents_district","district"),("ix_knowledge_documents_state","state"),("ix_knowledge_documents_status","status"),("ix_knowledge_documents_content_hash","content_hash")):
            op.create_index(name,"knowledge_documents",[column])
    if "knowledge_chunks" not in tables:
        op.create_table("knowledge_chunks",sa.Column("id",sa.String(),primary_key=True),sa.Column("document_id",sa.String(),sa.ForeignKey("knowledge_documents.id",ondelete="CASCADE"),nullable=False),
            sa.Column("ordinal",sa.Integer(),nullable=False),sa.Column("text",sa.Text(),nullable=False),sa.Column("embedding",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
        op.create_index("ix_knowledge_chunks_document_id","knowledge_chunks",["document_id"])

def downgrade():
    op.drop_index("ix_knowledge_chunks_document_id",table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    for name in ("ix_knowledge_documents_content_hash","ix_knowledge_documents_status","ix_knowledge_documents_state","ix_knowledge_documents_district","ix_knowledge_documents_category","ix_knowledge_documents_title"):
        op.drop_index(name,table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
