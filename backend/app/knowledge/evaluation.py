"""Small reproducible retrieval and citation metrics for reviewed benchmark cases."""
import math

def retrieval_metrics(cases,retrieve,top_k=5):
    totals={"recall_at_k":0.0,"precision_at_k":0.0,"mrr":0.0,"ndcg_at_k":0.0,"abstention_accuracy":0.0,"count":0,"abstention_count":0}
    for case in cases:
        relevant=set(case["relevant_document_ids"])
        rows=retrieve(case["query"],top_k,case.get("filters",{}))
        ranked=[row[2].id for row in rows]
        answerable=case.get("answerable",bool(relevant))
        totals["abstention_accuracy"]+=float(bool(rows)==answerable)
        totals["abstention_count"]+=1
        if not relevant:continue
        hits=[identifier in relevant for identifier in ranked]
        found=sum(hits)
        totals["recall_at_k"]+=found/len(relevant)
        totals["precision_at_k"]+=found/top_k
        totals["mrr"]+=next((1/(index+1) for index,hit in enumerate(hits) if hit),0.0)
        dcg=sum(1/math.log2(index+2) for index,hit in enumerate(hits) if hit)
        ideal=sum(1/math.log2(index+2) for index in range(min(top_k,len(relevant))))
        totals["ndcg_at_k"]+=dcg/ideal if ideal else 0.0
        totals["count"]+=1
    count=totals["count"]
    return {key:(value/count if count and key not in {"count","abstention_count","abstention_accuracy"} else value/totals["abstention_count"] if key=="abstention_accuracy" and totals["abstention_count"] else value) for key,value in totals.items()}

def claim_metrics(claims):
    total=len(claims)
    if not total:return {"citation_coverage":1.0,"claim_support_rate":1.0,"unsupported_claim_rate":0.0,"claim_count":0}
    cited=sum(bool(item.get("supporting_chunk")) for item in claims)
    supported=sum(item.get("entailment_status")=="SUPPORTED" for item in claims)
    return {"citation_coverage":cited/total,"claim_support_rate":supported/total,"unsupported_claim_rate":1-supported/total,"claim_count":total}
