"""Optional structured interview interpretation; never commits business data."""
from ..llm_client import LLMClient
from ..schemas import InterviewAnswer,InterviewTurn
from ...dialogue import SLOTS,normalize

SYSTEM_PROMPT=("You interpret one beneficiary interview turn. Return only the requested JSON. "
"Do not infer facts the beneficiary did not state, do not provide eligibility decisions, and do not invent government information. "
"The backend preserves the original answer separately; extract only explicit facts.")

class InterviewAIService:
    def __init__(self,client:LLMClient):self.client=client

    def interpret(self,*,session_id:str,slot:str,answer:str,language:str,input_method:str)->InterviewAnswer:
        if slot not in SLOTS:raise ValueError("Unknown interview slot")
        if language not in {"en","hi"}:raise ValueError("Unsupported language")
        if input_method not in {"text","browser_voice","server_transcription"}:raise ValueError("Unsupported input method")
        prompt=(f"Interview slot: {slot}\nLanguage: {language}\nOriginal answer: {answer}\n"
                "Return fields slot, answer, normalized_answer, language, input_method. Echo slot, answer, language, and input_method exactly. "
                "Normalize only what is explicit in the answer. For list-valued skills/interests/tools/constraints use a list; for travel distance use a number; otherwise use a concise string or null.")
        result=self.client.generate_json(prompt,InterviewAnswer,system=SYSTEM_PROMPT,operation="interview_interpret",session_id=session_id)
        # Hard business validation: the model cannot change the slot or evidence.
        if (result.slot,result.answer,result.language,result.input_method)!=(slot,answer,language,input_method):
            raise ValueError("AI output changed interview evidence")
        deterministic=normalize(slot,answer)
        if deterministic is not None:result.normalized_answer=deterministic
        return result

    def interpret_turn(self,*,session_id:str,answer:str,language:str,input_method:str,profile:dict)->InterviewTurn:
        if not answer.strip() or len(answer)>2000:raise ValueError("Invalid interview answer")
        if language not in {"en","hi"}:raise ValueError("Unsupported language")
        if input_method not in {"text","browser_voice","server_transcription"}:raise ValueError("Unsupported input method")
        # Only already validated profile values and the finite interview field set are context.
        prompt=(f"Language: {language}\nCurrent validated profile JSON: {profile}\n"
                f"Allowed fields: {', '.join(SLOTS)}\nOriginal answer: {answer}\n"
                "Return JSON with extracted (an object containing only facts explicitly present in this answer, using the allowed field names) "
                "and needs_clarification (true only when the answer cannot safely be mapped to the active interview question), "
                "plus confidence (a 0-to-1 estimate for each extracted field; this is your uncertainty estimate, not factual certainty). "
                "Do not infer age, eligibility, location, or experience. Skills/interests/tools/constraints must be lists of short strings. "
                "Use canonical skill ids only when unambiguous, e.g. basic_excel. Do not repeat existing profile list items.")
        result=self.client.generate_json(prompt,InterviewTurn,system=SYSTEM_PROMPT,operation="interview_turn",session_id=session_id)
        invalid=set(result.extracted.model_fields_set)-set(SLOTS)
        if invalid:raise ValueError("AI returned unsupported profile fields")
        return result
