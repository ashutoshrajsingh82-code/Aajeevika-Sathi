# Recommendation engine

This is a deterministic rules engine, not a trained model. It creates candidate pathways from the demo catalogue and ranks them with configurable weights: interests 30%, existing-skill overlap 25%, district-demand signal 20%, feasibility 15%, and stated work preference 10%. The numeric score is intentionally not shown to beneficiaries. The UI displays signals and decision evidence.

## Filters and unknowns

- A known travel distance over the beneficiary's stated maximum removes that pathway.
- Training prerequisites and minimum education are unverified for demo pathways. Eligibility is therefore “needs counsellor verification,” not a pass.
- A missing centre is disclosed. Demo centre locations are illustrative and not operational.
- The local demand seed is neutral and synthetic. It does not provide a real demand advantage.

## Skill gaps

Required skill labels in each sample pathway are compared with skills the person explicitly shared. The UI separates already-shared skills from skills to develop. Interests do not count as skills. No bridge course is suggested unless a verified bridge mapping is added.

## Explainability

Each result exposes signals for interest, skill overlap, demand, feasibility, preference, eligibility status, and the matched text terms. The implementation does not claim semantic embedding search, trained ranking, or accuracy measurements.
