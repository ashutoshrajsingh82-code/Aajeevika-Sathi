"""Add official-source provenance, originals, page chunks and optional pgvector."""
from alembic import op
import sqlalchemy as sa

revision="0007_provenance_and_page_chunks"
down_revision="0006_knowledge_rag"
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind()
    document_columns={column["name"] for column in sa.inspect(bind).get_columns("knowledge_documents")}
    document_additions=(
        ("source_url",sa.Column("source_url",sa.String(),nullable=True)),
        ("ministry",sa.Column("ministry",sa.String(),nullable=True)),
        ("department",sa.Column("department",sa.String(),nullable=True)),
        ("scheme_name",sa.Column("scheme_name",sa.String(),nullable=True)),
        ("document_type",sa.Column("document_type",sa.String(),nullable=True)),
        ("publication_date",sa.Column("publication_date",sa.String(),nullable=True)),
        ("language",sa.Column("language",sa.String(),nullable=False,server_default="unknown")),
        ("source_type",sa.Column("source_type",sa.String(),nullable=False,server_default="unknown")),
        ("verification_status",sa.Column("verification_status",sa.String(),nullable=False,server_default="UNKNOWN")),
        ("retrieved_at",sa.Column("retrieved_at",sa.DateTime(timezone=True),nullable=True)),
        ("supersedes_document_id",sa.Column("supersedes_document_id",sa.String(),nullable=True)),
        ("original_filename",sa.Column("original_filename",sa.String(),nullable=True)),
        ("original_content",sa.Column("original_content",sa.LargeBinary(),nullable=True)),
        ("extraction_status",sa.Column("extraction_status",sa.String(),nullable=False,server_default="text_only")),
        ("verified_by",sa.Column("verified_by",sa.String(),nullable=True)),
        ("verification_note",sa.Column("verification_note",sa.Text(),nullable=True)),
    )
    for name,column in document_additions:
        if name not in document_columns:op.add_column("knowledge_documents",column)
    if "ix_knowledge_documents_verification_status" not in {index["name"] for index in sa.inspect(bind).get_indexes("knowledge_documents")}:
        op.create_index("ix_knowledge_documents_verification_status","knowledge_documents",["verification_status"])
    chunk_columns={column["name"] for column in sa.inspect(bind).get_columns("knowledge_chunks")}
    for name,column in (("page_number",sa.Column("page_number",sa.Integer(),nullable=True)),("section",sa.Column("section",sa.String(),nullable=True)),("source_url",sa.Column("source_url",sa.String(),nullable=True))):
        if name not in chunk_columns:op.add_column("knowledge_chunks",column)
    if "embedding_model" not in chunk_columns:op.add_column("knowledge_chunks",sa.Column("embedding_model",sa.String(),nullable=False,server_default="local-feature-hash-v1"))
    op.execute("UPDATE knowledge_documents SET source_url = source WHERE source_url IS NULL")
    op.execute("UPDATE knowledge_documents SET verification_status = CASE WHEN status = 'DEMO' THEN 'UNKNOWN' WHEN status = 'STALE' THEN 'OFFICIAL_UNVERIFIED' ELSE 'OFFICIAL_UNVERIFIED' END")
    if bind.dialect.name=="postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_vector vector(256)")
        op.execute("UPDATE knowledge_chunks SET embedding_vector = embedding::text::vector WHERE embedding_vector IS NULL")
        op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_embedding_hnsw ON knowledge_chunks USING hnsw (embedding_vector vector_cosine_ops)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_chunks_fts_gin ON knowledge_chunks USING gin (to_tsvector('simple', text))")

def downgrade():
    bind=op.get_bind()
    if bind.dialect.name=="postgresql":
        op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_fts_gin")
        op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw")
        op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS embedding_vector")
    op.drop_index("ix_knowledge_documents_verification_status",table_name="knowledge_documents")
    for name in ("embedding_model","source_url","section","page_number"):
        if name in {column["name"] for column in sa.inspect(bind).get_columns("knowledge_chunks")}:op.drop_column("knowledge_chunks",name)
    for name in ("verification_note","verified_by","extraction_status","original_content","original_filename","supersedes_document_id","retrieved_at","verification_status","source_type","language","publication_date","document_type","scheme_name","department","ministry","source_url"):
        if name in {column["name"] for column in sa.inspect(bind).get_columns("knowledge_documents")}:op.drop_column("knowledge_documents",name)
