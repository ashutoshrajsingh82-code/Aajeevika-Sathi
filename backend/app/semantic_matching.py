"""Small, deterministic local semantic matcher with a provider seam for embeddings later."""
from abc import ABC,abstractmethod
import math,re

SEMANTIC_MODEL_VERSION="curated-concepts-char-ngrams-v1"
CONCEPTS={
    "digital_computing":{"computer","computers","basic computer","computer knowledge","computer use","computer chalana","computer चलाना","digital","digital forms","digital services","computer work","computer literacy","basic_computer"},
    "spreadsheets":{"excel","ms excel","basic excel","spreadsheet","spreadsheets","basic_excel"},
    "office_software":{"ms office","microsoft office","office software","word processing","ms_office"},
    "apparel":{"tailoring","tailor","stitching","sewing","garment","garments","apparel","measurement","textile","दर्जी","सिलाई","कपड़ा"},
    "electrical":{"electrical","electricity","wiring","electronics","solar","repair","बिजली","इलेक्ट्रिक","सौर","मरम्मत"},
    "agriculture":{"agriculture","farming","farm","crops","livestock","खेती","कृषि"},
    "food":{"food","cooking","bakery","catering","food processing","खाना","खाद्य"},
    "beauty":{"beauty","salon","grooming","सुंदरता","ब्यूटी"},
    "sales_service":{"retail","sales","customer service","shop assistant","mobile services"},
}
_ALIAS_TO_CONCEPT={alias.casefold():concept for concept,aliases in CONCEPTS.items() for alias in aliases}
SKILL_EQUIVALENTS={
    "basic_computer":{"basic computer","basic computer use","computer","computer knowledge","computer use","computer chalana","computer चलाना","computer literacy","basic_computer"},
    "basic_excel":{"excel","ms excel","basic excel","spreadsheet","spreadsheets","basic_excel"},
    "ms_office":{"ms office","microsoft office","office software","ms_office"},
    "basic_stitching":{"stitching","sewing","basic stitching","basic sewing"},
}
_SKILL_CANONICAL={alias.casefold():canonical for canonical,aliases in SKILL_EQUIVALENTS.items() for alias in aliases}

def equivalent_skill(left,right):
    a=" ".join(str(left or "").casefold().replace("_"," ").split())
    b=" ".join(str(right or "").casefold().replace("_"," ").split())
    return a==b or (_SKILL_CANONICAL.get(a) is not None and _SKILL_CANONICAL.get(a)==_SKILL_CANONICAL.get(b))

def _terms(text):
    raw=" ".join(str(text or "").casefold().replace("_"," ").split())
    tokens=set(re.findall(r"[\w]+",raw,flags=re.UNICODE))
    concepts={concept for alias,concept in _ALIAS_TO_CONCEPT.items() if alias in raw}
    return raw,tokens,concepts

def _features(text):
    raw,tokens,concepts=_terms(text)
    result={f"token:{token}":1.0 for token in tokens}
    result.update({f"concept:{concept}":2.0 for concept in concepts})
    padded=f"  {raw}  "
    for i in range(max(0,len(padded)-2)):
        gram=padded[i:i+3]
        if len(gram.strip())>=2:result[f"tri:{gram}"]=result.get(f"tri:{gram}",0)+0.35
    return result,concepts

class SemanticMatcher(ABC):
    model_version="semantic-unknown"
    @abstractmethod
    def similarity(self,left:str,right:str)->float:...

class LocalSemanticMatcher(SemanticMatcher):
    """Curated cross-language concepts plus character n-gram cosine; no network/model download."""
    model_version=SEMANTIC_MODEL_VERSION
    def similarity(self,left,right):
        a,ac=_features(left);b,bc=_features(right)
        if not a or not b:return 0.0
        dot=sum(value*b.get(key,0.0) for key,value in a.items())
        norm_a=math.sqrt(sum(v*v for v in a.values()));norm_b=math.sqrt(sum(v*v for v in b.values()))
        cosine=dot/(norm_a*norm_b) if norm_a and norm_b else 0.0
        concept=(len(ac&bc)/math.sqrt(len(ac)*len(bc))) if ac and bc else 0.0
        return round(max(0.0,min(1.0,0.65*concept+0.35*cosine)),6)
