"""Provider-neutral embedding interface with a deterministic local fallback."""
from abc import ABC,abstractmethod
import hashlib,re,math,os
import httpx

class EmbeddingProvider(ABC):
    model_version="abstract"
    @abstractmethod
    def embed(self,text:str)->list[float]:...

class LocalHashEmbedding(EmbeddingProvider):
    """Small deterministic feature-hash vectorizer; replaceable by an embedding provider."""
    model_version="local-feature-hash-v1"
    dimensions=256
    def embed(self,text:str)->list[float]:
        vector=[0.0]*self.dimensions
        tokens=re.findall(r"[\w\u0900-\u097f]+",text.casefold())
        features=tokens[:]
        for token in tokens:
            features.extend(token[i:i+3] for i in range(max(0,len(token)-2)))
        for feature in features:
            digest=hashlib.blake2b(feature.encode("utf-8"),digest_size=8).digest()
            index=int.from_bytes(digest[:4],"big")%self.dimensions
            sign=1.0 if digest[4]&1 else -1.0
            vector[index]+=sign
        norm=math.sqrt(sum(value*value for value in vector))
        return [value/norm for value in vector] if norm else vector

class OpenAICompatibleEmbedding(EmbeddingProvider):
    """Optional OpenAI-compatible embedding endpoint; vector size is checked for pgvector compatibility."""
    def __init__(self,base_url:str,model:str,api_key:str|None=None,dimensions:int=256,timeout:float=20.0,transport=None):
        self.base_url=base_url.rstrip("/");self.model=model;self.api_key=api_key;self.dimensions=dimensions;self.timeout=timeout;self.transport=transport
        self.model_version=f"{model}:{dimensions}"
    def embed(self,text:str)->list[float]:
        headers={"Authorization":f"Bearer {self.api_key}"} if self.api_key else {}
        payload={"model":self.model,"input":text,"dimensions":self.dimensions}
        with httpx.Client(timeout=self.timeout,transport=self.transport) as client:
            response=client.post(self.base_url+"/embeddings",headers=headers,json=payload)
        response.raise_for_status();vector=response.json()["data"][0]["embedding"]
        if not isinstance(vector,list) or len(vector)!=self.dimensions:raise ValueError("Embedding provider returned a vector with an unexpected dimension")
        return [float(value) for value in vector]

def create_embedding_provider(environ=None):
    env=os.environ if environ is None else environ
    provider=env.get("EMBEDDING_PROVIDER","hash").strip().lower()
    if provider in {"hash","local"}:return LocalHashEmbedding()
    if provider not in {"openai_compatible","ollama"}:raise ValueError("EMBEDDING_PROVIDER must be hash, openai_compatible, or ollama")
    base=env.get("EMBEDDING_BASE_URL",env.get("AI_BASE_URL","http://localhost:11434/v1")).rstrip("/")
    model=env.get("EMBEDDING_MODEL","").strip()
    if not model:raise ValueError("EMBEDDING_MODEL is required for remote embeddings")
    dimensions=int(env.get("EMBEDDING_DIMENSIONS","256"))
    if not 1<=dimensions<=4096:raise ValueError("EMBEDDING_DIMENSIONS must be between 1 and 4096")
    return OpenAICompatibleEmbedding(base,model,env.get("AI_API_KEY"),dimensions)

def cosine(left:list[float],right:list[float])->float:
    if not left or len(left)!=len(right):return 0.0
    return sum(a*b for a,b in zip(left,right))
