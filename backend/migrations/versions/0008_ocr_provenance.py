"""Persist OCR runtime, language, confidence and actionable extraction state."""
from alembic import op
import sqlalchemy as sa

revision="0008_ocr_provenance"
down_revision="0007_provenance_and_page_chunks"
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind()
    present={column["name"] for column in sa.inspect(bind).get_columns("knowledge_documents")}
    additions=(
        ("ocr_used",sa.Column("ocr_used",sa.Boolean(),nullable=False,server_default=sa.false())),
        ("ocr_engine",sa.Column("ocr_engine",sa.String(),nullable=True)),
        ("ocr_language",sa.Column("ocr_language",sa.String(),nullable=True)),
        ("ocr_confidence",sa.Column("ocr_confidence",sa.Float(),nullable=True)),
        ("ocr_available",sa.Column("ocr_available",sa.Boolean(),nullable=True)),
        ("ocr_reviewed",sa.Column("ocr_reviewed",sa.Boolean(),nullable=False,server_default=sa.false())),
        ("extraction_message",sa.Column("extraction_message",sa.Text(),nullable=True)),
    )
    for name,column in additions:
        if name not in present:op.add_column("knowledge_documents",column)
    chunk_columns={column["name"] for column in sa.inspect(bind).get_columns("knowledge_chunks")}
    for name,column in (("ocr_used",sa.Column("ocr_used",sa.Boolean(),nullable=False,server_default=sa.false())),("ocr_language",sa.Column("ocr_language",sa.String(),nullable=True)),("ocr_confidence",sa.Column("ocr_confidence",sa.Float(),nullable=True))):
        if name not in chunk_columns:op.add_column("knowledge_chunks",column)

def downgrade():
    bind=op.get_bind()
    present={column["name"] for column in sa.inspect(bind).get_columns("knowledge_documents")}
    for name in ("extraction_message","ocr_available","ocr_confidence","ocr_language","ocr_engine","ocr_used"):
        if name in present:op.drop_column("knowledge_documents",name)
    chunks={column["name"] for column in sa.inspect(bind).get_columns("knowledge_chunks")}
    for name in ("ocr_confidence","ocr_language","ocr_used"):
        if name in chunks:op.drop_column("knowledge_chunks",name)
    if "ocr_reviewed" in present:op.drop_column("knowledge_documents","ocr_reviewed")
