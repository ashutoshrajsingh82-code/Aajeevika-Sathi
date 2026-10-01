"""Vector storage seam. SQLAlchemy implementation works with current SQLite/PostgreSQL DBs."""
from abc import ABC,abstractmethod
from sqlalchemy.orm import Session
from .embeddings import cosine
from ..models import KnowledgeChunk,KnowledgeDocument

class VectorStore(ABC):
    @abstractmethod
    def add(self,chunk:KnowledgeChunk):...
    @abstractmethod
    def search(self,db:Session,query_vector:list[float],limit:int=5,filters:dict|None=None):...

class SQLAlchemyVectorStore(VectorStore):
    """Portable JSON-vector backend; can be replaced by pgvector without changing retrieval."""
    def add(self,chunk):return chunk
    def search(self,db,query_vector,limit=5,filters=None):
        filters=filters or {}
        query=db.query(KnowledgeChunk,KnowledgeDocument).join(KnowledgeDocument,KnowledgeChunk.document_id==KnowledgeDocument.id)
        query=query.filter(KnowledgeDocument.status!="UNKNOWN")
        for key in ("category","district","state","status"):
            value=filters.get(key)
            if value:
                column=getattr(KnowledgeDocument,key)
                query=query.filter(column.ilike(value) if key in {"district","state"} else column==value)
        ranked=[]
        for chunk,document in query.all():
            score=cosine(query_vector,chunk.embedding or [])
            if score>0:ranked.append((score,chunk,document))
        ranked.sort(key=lambda item:(item[0],item[2].last_verified or "",item[2].id),reverse=True)
        return ranked[:max(1,min(limit,20))]
