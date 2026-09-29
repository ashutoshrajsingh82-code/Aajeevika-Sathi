from abc import ABC,abstractmethod
import os

class SpeechProvider(ABC):
    @abstractmethod
    async def transcribe(self,audio:bytes,filename:str,language:str)->dict: ...
    @abstractmethod
    async def synthesize(self,text:str,language:str)->dict: ...

class WhisperSpeechProvider(SpeechProvider):
    async def transcribe(self,audio,filename,language):
        try:
            import tempfile, whisper
            with tempfile.NamedTemporaryFile(suffix=".webm") as f:
                f.write(audio);f.flush();model=whisper.load_model("base")
                result=model.transcribe(f.name,language="hi" if language=="hi" else "en")
            return {"transcript":result.get("text","").strip(),"provider":"whisper","confidence":None}
        except Exception:
            return {"transcript":"","provider":"fallback","confidence":None,"message":"Whisper is unavailable. Use browser speech recognition or type your answer."}
    async def synthesize(self,text,language):
        return {"text":text,"provider":"browser-speech-synthesis","audio_url":None}

class BhashiniSpeechProvider(SpeechProvider):
    async def transcribe(self,audio,filename,language):
        if not os.getenv("BHASHINI_API_KEY") or not os.getenv("BHASHINI_API_URL"):
            return {"transcript":"","provider":"fallback","message":"Bhashini credentials are not configured. Use browser voice or text."}
        return {"transcript":"","provider":"bhashini-adapter","message":"Configure the deployment-specific Bhashini task pipeline to enable server transcription."}
    async def synthesize(self,text,language): return {"text":text,"provider":"browser-speech-synthesis","audio_url":None}
