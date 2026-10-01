"""Conservative claim-to-passage validation; unsupported generated text is never surfaced."""
from abc import ABC,abstractmethod
import re

STOP={"the","a","an","and","or","is","are","was","were","be","to","of","in","on","for","as","by","with","from","that","this","it","its","at","can","may","must","will","do","does","not","only","under","within","per","आदि","है","का","की","के","में","को","और","पर"}

class EntailmentChecker(ABC):
    @abstractmethod
    def verify(self,claim:str,evidence:str)->dict:...

class LexicalEntailmentChecker(EntailmentChecker):
    """High-precision lexical check; this is not a general natural-language theorem prover."""
    def verify(self,claim,evidence):
        claim_norm=_normalize(claim);evidence_norm=_normalize(evidence)
        if claim_norm and claim_norm in evidence_norm:return {"support_score":1.0,"entailment_status":"SUPPORTED"}
        tokens=_content_tokens(claim);evidence_tokens=_content_tokens(evidence)
        if not tokens:return {"support_score":0.0,"entailment_status":"UNSUPPORTED"}
        required_numbers=set(re.findall(r"\d+(?:[,.]\d+)*%?",claim))
        found_numbers=set(re.findall(r"\d+(?:[,.]\d+)*%?",evidence))
        score=len(tokens & evidence_tokens)/len(tokens)
        if required_numbers and not required_numbers.issubset(found_numbers):score=0.0
        claim_neg=bool(re.search(r"\b(no|not|never|none|नहीं|नही)\b",claim.casefold()))
        evidence_neg=bool(re.search(r"\b(no|not|never|none|नहीं|नही)\b",evidence.casefold()))
        if claim_neg!=evidence_neg:score=0.0
        status="SUPPORTED" if score>=.88 else "PARTIALLY_SUPPORTED" if score>=.55 else "UNSUPPORTED"
        return {"support_score":round(score,4),"entailment_status":status}

def _normalize(text):return " ".join(re.findall(r"[\w\u0900-\u097f]+",text.casefold()))
def _content_tokens(text):return {token for token in re.findall(r"[\w\u0900-\u097f]+",text.casefold()) if token not in STOP and len(token)>1}

def split_claims(answer:str)->list[str]:
    return [part.strip(" •\t\n") for part in re.split(r"(?<=[.!?।])\s+|\n+",answer) if part.strip(" •\t\n")]

def validate_claims(claims,retrieved_hits,checker=None):
    checker=checker or LexicalEntailmentChecker();by_id={hit["chunk_id"]:hit for hit in retrieved_hits};accepted=[];rejected=[]
    for claim in claims:
        text=claim.get("text","").strip()
        for citation_id in claim.get("cited_chunk_ids",[]):
            hit=by_id.get(citation_id)
            if not hit:continue
            verdict=checker.verify(text,hit["text"])
            record={"claim":text,"supporting_chunk":citation_id,"support_score":verdict["support_score"],"entailment_status":verdict["entailment_status"]}
            if verdict["entailment_status"]=="SUPPORTED":accepted.append(record);break
            rejected.append(record)
    return accepted,rejected
