# Evaluation status

## Implemented checks

- Unit checks cover deterministic state progression, consent, skill-gap separation, unknown eligibility handling, and travel-limit filtering.
- API health is `GET /health` and returns `{"status":"ok", ...}`.
- The guided demo uses synthetic personas and no external credentials.

## Not yet validated

- No real audio/dialect test set is included; WER and slot-extraction accuracy are not measured.
- No field pilot, recommendation acceptance study, employment result, placement result, fairness study, or government integration exists.
- Real catalogue currency, centre operations, travel time, demand and capacity require external verification.

Use `python -m pytest backend/tests -q` from the repository root after installing backend requirements. Add appropriately consented test data before reporting empirical results.
