"""Privacy-safe structured operational logging for AI calls."""
import json,logging
logger=logging.getLogger("aajeevika.ai")

def record_event(*,request_id:str,session_id:str|None,operation:str,model:str,latency_ms:float,outcome:str,validation_failure:bool=False,prompt_tokens:int|None=None,completion_tokens:int|None=None):
    logger.info(json.dumps({"event":"ai_operation","request_id":request_id,"session_id":session_id,"operation":operation,"model":model,"latency_ms":round(latency_ms,2),"outcome":outcome,"validation_failure":validation_failure,"prompt_tokens":prompt_tokens,"completion_tokens":completion_tokens},separators=(",",":")))
