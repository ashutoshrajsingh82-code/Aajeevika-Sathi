"""Common retrieval contracts and lexical, JSON-hash, pgvector, and hybrid retrievers."""
from abc import ABC,abstractmethod
from collections import Counter
import math,re
from sqlalchemy import text,func
from sqlalchemy.orm import Session
from ..models import KnowledgeChunk,KnowledgeDocument
from .embeddings import LocalHashEmbedding,cosine

class Retriever(ABC):
    @abstractmethod
    def retrieve(self,db:Session,query:str,top_k:int=5,filters:dict|None=None):...

class QueryClassifier:
    RULES={
        "ELIGIBILITY":("eligible","eligibility","who can apply","पात्रता","patra","kaun apply"),
        "BENEFITS":("benefit","financial assistance","monetary","amount","subsidy","grant","financial support","लाभ","राशि","paise","madad"),
        "APPLICATION_PROCESS":("apply","application","how to get","procedure","process","आवेदन","कैसे apply"),
        "DOCUMENTS_REQUIRED":("documents","document required","certificate","दस्तावेज"),
        "TRAINING":("course","training","qualification","skill","कौशल","training centre"),
        "LIVELIHOOD":("livelihood","employment","enterprise","income","रोजगार","आजीविका"),
        "LOCAL_OPPORTUNITIES":("district","local","nearby","centre","center","स्थानीय","जिला"),
        "SCHEME_INFORMATION":("scheme","yojana","guideline","policy","योजना"),
    }
    CATEGORY={"TRAINING":"course","LIVELIHOOD":"district_livelihood","LOCAL_OPPORTUNITIES":"training_centre","SCHEME_INFORMATION":"scheme","ELIGIBILITY":"eligibility","BENEFITS":"scheme","APPLICATION_PROCESS":"scheme","DOCUMENTS_REQUIRED":"scheme"}
    @classmethod
    def classify(cls,query:str)->dict:
        folded=query.casefold();kind=next((name for name,terms in cls.RULES.items() if any(term in folded for term in terms)),"GENERAL")
        return {"intent":kind,"category":cls.CATEGORY.get(kind)}

_SYNONYMS={
    "financial assistance":{"financial","monetary","money","benefit","support","aid","grant","subsidy","सहायता","राशि","पैसा","मदद"},
    "eligibility":{"eligible","qualification","criteria","पात्रता","योग्यता"},
    "apply":{"application","enrol","register","आवेदन","पंजीकरण"},
    "training":{"course","skill","learning","कौशल","प्रशिक्षण"},
}
_STOP={"what","does","this","the","is","are","for","of","a","an","to","can","how","much","this","scheme","provide","do","i","get","या","है","क्या","के","की","का","में","demo","data","sample","synthetic","official"}

def query_terms(query:str)->set[str]:
    terms=set(re.findall(r"[\w\u0900-\u097f]+",query.casefold()))-_STOP
    expanded=set(terms)
    for root,synonyms in _SYNONYMS.items():
        if root in terms or terms.intersection(synonyms):expanded.update(synonyms);expanded.update(root.split())
    return expanded

def _eligible_query(db,filters):
    query=db.query(KnowledgeChunk,KnowledgeDocument).join(KnowledgeDocument,KnowledgeChunk.document_id==KnowledgeDocument.id)
    query=query.filter((KnowledgeDocument.status.in_(["DEMO","STALE"]))|(KnowledgeDocument.verification_status.in_(["OFFICIAL_VERIFIED","SECONDARY_SOURCE"])))
    for key in ("category","district","state","scheme_name","verification_status"):
        value=(filters or {}).get(key)
        if value:
            column=getattr(KnowledgeDocument,key)
            query=query.filter(column.ilike(value) if key in {"district","state","scheme_name"} else column==value)
    return query

class HashRetriever(Retriever):
    def __init__(self,embedder=None):self.embedder=embedder or LocalHashEmbedding()
    def retrieve(self,db,query,top_k=5,filters=None):
        vector=self.embedder.embed(query);ranked=[]
        for chunk,doc in _eligible_query(db,filters).all():
            if chunk.embedding_model and chunk.embedding_model!=self.embedder.model_version:continue
            score=max(0.0,cosine(vector,chunk.embedding or []))
            if score>0:ranked.append((score,chunk,doc))
        ranked.sort(key=lambda result:(result[0],result[2].last_verified or ""),reverse=True)
        return ranked[:max(1,min(top_k,20))]

class LexicalRetriever(Retriever):
    def retrieve(self,db,query,top_k=5,filters=None):
        terms=query_terms(query)
        if not terms:return []
        if db.get_bind().dialect.name=="postgresql":
            queryable=_eligible_query(db,filters)
            tsquery=" ".join(sorted(terms))
            ranked=queryable.with_entities(KnowledgeChunk,KnowledgeDocument,func.ts_rank_cd(func.to_tsvector("simple",KnowledgeChunk.text),func.plainto_tsquery("simple",tsquery)).label("rank"))
            ranked=ranked.filter(func.to_tsvector("simple",KnowledgeChunk.text).op("@@")(func.plainto_tsquery("simple",tsquery))).order_by(text("rank DESC")).limit(max(1,min(top_k,20)))
            return [(float(rank),chunk,doc) for chunk,doc,rank in ranked.all()]
        candidates=_eligible_query(db,filters).all();doc_freq=Counter();tokenized=[]
        for chunk,doc in candidates:
            tokens=query_terms(chunk.text);tokenized.append((chunk,doc,tokens));doc_freq.update(terms&tokens)
        ranked=[]
        for chunk,doc,tokens in tokenized:
            matched=terms&tokens
            if not matched:continue
            coverage=len(matched)/max(1,len(terms))
            idf=sum(math.log(1+(len(tokenized)-doc_freq[t]+.5)/(doc_freq[t]+.5)) for t in matched)/len(matched)
            lexical_score=coverage*(.7+.3*min(1.0,idf/3))
            ranked.append((lexical_score,chunk,doc))
        ranked.sort(key=lambda item:item[0],reverse=True)
        return ranked[:max(1,min(top_k,20))]

class PgVectorRetriever(Retriever):
    """PostgreSQL pgvector cosine retrieval (requires migration 0007 and VECTOR_STORE=pgvector)."""
    def __init__(self,embedder):self.embedder=embedder
    def retrieve(self,db,query,top_k=5,filters=None):
        if db.get_bind().dialect.name!="postgresql":raise RuntimeError("pgvector retrieval requires PostgreSQL")
        vector=self.embedder.embed(query)
        clauses=["(d.status IN ('DEMO','STALE') OR d.verification_status IN ('OFFICIAL_VERIFIED','SECONDARY_SOURCE'))"]
        params={"vector":"["+",".join(str(value) for value in vector)+"]","limit":max(1,min(top_k,20))}
        for key in ("category","district","state","scheme_name","verification_status"):
            value=(filters or {}).get(key)
            if value:
                clauses.append(f"d.{key} = :{key}" if key not in {"district","state","scheme_name"} else f"lower(d.{key}) = lower(:{key})")
                params[key]=value
        sql="SELECT c.id, 1 - (c.embedding_vector <=> CAST(:vector AS vector)) AS score FROM knowledge_chunks c JOIN knowledge_documents d ON d.id=c.document_id WHERE "+" AND ".join(clauses)+" ORDER BY c.embedding_vector <=> CAST(:vector AS vector) LIMIT :limit"
        rows=db.execute(text(sql),params).all();ids=[row.id for row in rows]
        if not ids:return []
        objects={chunk.id:(chunk,doc) for chunk,doc in _eligible_query(db,filters).filter(KnowledgeChunk.id.in_(ids)).all()}
        return [(float(row.score),*objects[row.id]) for row in rows if row.id in objects]

class HybridRetriever(Retriever):
    def __init__(self,vector_retriever:Retriever|None=None,embedder=None,lexical_retriever:Retriever|None=None,lexical_weight:float=.45):
        self.vector_retriever=vector_retriever or HashRetriever(embedder)
        self.lexical_retriever=lexical_retriever or LexicalRetriever()
        self.lexical_weight=lexical_weight
    def retrieve(self,db,query,top_k=5,filters=None):
        lexical=self.lexical_retriever.retrieve(db,query,top_k=max(top_k*4,12),filters=filters)
        try:vector_hits=self.vector_retriever.retrieve(db,query,top_k=max(top_k*4,12),filters=filters)
        except Exception:vector_hits=[]
        scores={}
        objects={}
        def add(rankscore,row,weight):
            score,chunk,doc=row;objects[chunk.id]=(chunk,doc);scores[chunk.id]=scores.get(chunk.id,0.0)+weight*max(0.0,score)
        for score,chunk,doc in lexical[:max(top_k*4,12)]:add((score,chunk,doc),(score,chunk,doc),self.lexical_weight)
        for rank,(score,chunk,doc) in enumerate(vector_hits):
            normalized=max(0.0,min(1.0,score))
            add((score,chunk,doc),(normalized,chunk,doc),1-self.lexical_weight)
        ranked=[]
        for chunk_id,score in scores.items():
            chunk,doc=objects[chunk_id]
            if score>=.08:ranked.append((min(score,1.0),chunk,doc))
        ranked.sort(key=lambda item:(item[0],item[2].last_verified or ""),reverse=True)
        return ranked[:max(1,min(top_k,20))]

def make_retriever(db,embedder=None):
    import os
    store=os.getenv("VECTOR_STORE","json").strip().lower()
    mode=os.getenv("RETRIEVAL_MODE","hybrid").strip().lower()
    if store not in {"json","pgvector"}:raise ValueError("VECTOR_STORE must be json or pgvector")
    if mode not in {"hybrid","hash","vector"}:raise ValueError("RETRIEVAL_MODE must be hybrid, hash, or vector")
    if mode=="hash":return HashRetriever(embedder)
    vector=PgVectorRetriever(embedder) if store=="pgvector" else HashRetriever(embedder)
    if mode=="vector":return vector
    return HybridRetriever(vector,embedder)
