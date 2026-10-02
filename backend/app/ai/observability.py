"""Privacy-safe structured operational metrics for AI calls."""
import json
import logging
from ..db import SessionLocal
from ..models import AIOperationMetric

logger=logging.getLogger("aajeevika.ai")

def record_event(*,request_id:str,session_id:str|None,operation:str,model:str,latency_ms:float,outcome:str,
                 validation_failure:bool=False,prompt_tokens:int|None=None,completion_tokens:int|None=None,
                 event_kind:str="operation"):
    payload={"event":"ai_operation","request_id":request_id,"session_id":session_id,"operation":operation,
             "model":model,"event_kind":event_kind,"latency_ms":round(latency_ms,2),"outcome":outcome,
             "validation_failure":validation_failure,"prompt_tokens":prompt_tokens,"completion_tokens":completion_tokens}
    logger.info(json.dumps(payload,separators=(",",":")))
    try:
        db=SessionLocal()
        try:
            db.add(AIOperationMetric(
                request_id=request_id,session_id=session_id,operation=operation,model=model,
                event_kind=event_kind,latency_ms=float(latency_ms),outcome=outcome,
                validation_failure=validation_failure,prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens))
            db.commit()
        finally:
            db.close()
    except Exception:
        # Observability must never break an otherwise valid AI request.
        logger.exception("Failed to persist AI operation metric")
