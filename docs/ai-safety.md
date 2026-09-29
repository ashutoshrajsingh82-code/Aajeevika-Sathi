# AI safety and grounding

The interview is a fixed slot sequence. The backend normalizes answers into a structured profile; it does not allow free-form LLM output to update database records. There is no LLM dependency in the current prototype.

Recommendations come from rows seeded in the pathway catalogue. Seeded entries are demo pathway concepts, not official course names. The system labels every result simulated and avoids asserting eligibility, fees, duration, opening, placement or scheme coverage. Unknown programme questions should be referred to the counsellor.

Speech recognition is optional. Whisper is loaded only if installed; missing model/runtime falls back to browser recognition or text. The Bhashini class is an adapter seam and does not make a network request until an endpoint-specific pipeline is configured. Text-to-speech uses browser synthesis.

There are no measured ASR accuracy, employment, placement, recommendation quality or fairness outcomes. Synthetic data must not be represented as pilot evidence.
