"""Small provider-neutral chat client with strict structured-output validation."""
from abc import ABC,abstractmethod
import json,re,time,uuid
from typing import TypeVar
import httpx
from pydantic import BaseModel,ValidationError
from .config import AISettings
from .observability import record_event

T=TypeVar("T",bound=BaseModel)

class AIError(RuntimeError):pass
class AIUnavailable(AIError):pass
class AIProviderError(AIError):pass
class InvalidModelJSON(AIError):pass
class OutputValidationError(AIError):pass

class LLMClient(ABC):
    @abstractmethod
    def generate(self,prompt:str,*,system:str="",operation:str="generate",session_id:str|None=None)->str:...

    def generate_json(self,prompt:str,schema:type[T],*,system:str="",operation:str="generate_json",session_id:str|None=None)->T:
        request_id=str(uuid.uuid4());start=time.perf_counter();validation_failure=False;outcome="provider_error";usage=getattr(self,"last_usage",{"prompt_tokens":None,"completion_tokens":None})
        try:
            schema_prompt=(prompt+"\n\nReturn only one JSON object matching this schema. Do not include markdown or extra fields:\n"+json.dumps(schema.model_json_schema(),ensure_ascii=False))
            raw=self.generate(schema_prompt,system=system,operation=operation,session_id=session_id)
            usage=getattr(self,"last_usage",usage)
            text=raw.strip()
            fenced=re.fullmatch(r"```(?:json)?\s*(.*?)\s*```",text,re.IGNORECASE|re.DOTALL)
            if fenced:text=fenced.group(1)
            try:data=json.loads(text)
            except (json.JSONDecodeError,TypeError) as exc:
                validation_failure=True;outcome="invalid_json";raise InvalidModelJSON("The AI provider returned invalid JSON") from exc
            try:result=schema.model_validate(data)
            except ValidationError as exc:
                validation_failure=True;outcome="schema_invalid";raise OutputValidationError("The AI response did not match the required schema") from exc
            outcome="success"
            return result
        except AIUnavailable:
            outcome="unavailable";raise
        except AIProviderError:
            outcome="provider_error";raise
        except AIError:
            raise
        finally:
            record_event(request_id=request_id,session_id=session_id,operation=operation,model=getattr(getattr(self,"settings",None),"model","disabled"),latency_ms=(time.perf_counter()-start)*1000,outcome=outcome,validation_failure=validation_failure,prompt_tokens=usage.get("prompt_tokens"),completion_tokens=usage.get("completion_tokens"),event_kind="structured_validation")

class OpenAICompatibleClient(LLMClient):
    """OpenAI chat-completions-compatible endpoint; works with compatible local servers."""
    def __init__(self,settings:AISettings,transport:httpx.BaseTransport|None=None):
        self.settings=settings;self.transport=transport;self.last_usage={"prompt_tokens":None,"completion_tokens":None}

    def generate(self,prompt:str,*,system:str="",operation:str="generate",session_id:str|None=None)->str:
        request_id=str(uuid.uuid4());started=time.perf_counter();outcome="provider_error";validation_failure=False
        headers={"Authorization":f"Bearer {self.settings.api_key}"} if self.settings.api_key else {}
        messages=[]
        if system:messages.append({"role":"system","content":system})
        messages.append({"role":"user","content":prompt})
        body={"model":self.settings.model,"messages":messages,"temperature":self.settings.temperature,"max_tokens":self.settings.max_tokens}
        self.last_usage={"prompt_tokens":None,"completion_tokens":None}
        try:
            with httpx.Client(timeout=self.settings.timeout_seconds,transport=self.transport) as client:
                response=client.post(f"{self.settings.base_url}/chat/completions",headers=headers,json=body)
            response.raise_for_status();payload=response.json()
            content=payload["choices"][0]["message"]["content"]
            if not isinstance(content,str) or not content.strip():raise AIProviderError("AI provider returned an empty response")
            usage=payload.get("usage") or {}
            self.last_usage={"prompt_tokens":usage.get("prompt_tokens"),"completion_tokens":usage.get("completion_tokens")}
            outcome="success"
            return content
        except httpx.TimeoutException as exc:
            outcome="timeout";raise AIUnavailable("AI provider timed out") from exc
        except httpx.HTTPStatusError as exc:
            outcome="provider_error";raise AIProviderError(f"AI provider returned HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError,ValueError,KeyError,IndexError,TypeError) as exc:
            outcome="provider_error";raise AIProviderError("AI provider response could not be read") from exc
        finally:
            usage=self.last_usage
            record_event(request_id=request_id,session_id=session_id,operation=operation,model=self.settings.model,latency_ms=(time.perf_counter()-started)*1000,outcome=outcome,validation_failure=validation_failure,prompt_tokens=usage["prompt_tokens"],completion_tokens=usage["completion_tokens"],event_kind="provider_call")

class DisabledLLMClient(LLMClient):
    def generate(self,prompt:str,*,system:str="",operation:str="generate",session_id:str|None=None)->str:
        raise AIUnavailable("AI provider is not configured")

def create_llm_client(settings:AISettings|None=None,transport:httpx.BaseTransport|None=None)->LLMClient:
    settings=settings or AISettings.from_env()
    if settings.provider=="disabled":return DisabledLLMClient()
    return OpenAICompatibleClient(settings,transport=transport)
