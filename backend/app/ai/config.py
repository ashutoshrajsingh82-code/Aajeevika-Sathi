"""Environment-only AI configuration; secrets are never embedded in code."""
from dataclasses import dataclass
import os

@dataclass(frozen=True)
class AISettings:
    provider:str="disabled"
    model:str=""
    base_url:str=""
    api_key:str|None=None
    temperature:float=0.2
    max_tokens:int=700
    timeout_seconds:float=20.0

    @classmethod
    def from_env(cls,environ=None):
        env=os.environ if environ is None else environ
        provider=env.get("AI_PROVIDER","disabled").strip().lower()
        if provider not in {"disabled","openai_compatible","ollama"}:raise ValueError("AI_PROVIDER must be disabled, openai_compatible, or ollama")
        try:
            temperature=float(env.get("AI_TEMPERATURE","0.2"));max_tokens=int(env.get("AI_MAX_TOKENS","700"));timeout=float(env.get("AI_TIMEOUT_SECONDS","20"))
        except ValueError as exc:raise ValueError("AI numeric settings must be valid numbers") from exc
        if not 0<=temperature<=2:raise ValueError("AI_TEMPERATURE must be between 0 and 2")
        if not 1<=max_tokens<=8192:raise ValueError("AI_MAX_TOKENS must be between 1 and 8192")
        if not 0.1<=timeout<=120:raise ValueError("AI_TIMEOUT_SECONDS must be between 0.1 and 120")
        model=env.get("AI_MODEL","").strip();base=env.get("AI_BASE_URL","").strip().rstrip("/")
        if provider!="disabled" and (not model or not base):raise ValueError("AI_MODEL and AI_BASE_URL are required when AI_PROVIDER is enabled")
        key=env.get("AI_API_KEY")
        return cls(provider,model,base,key if key else None,temperature,max_tokens,timeout)
