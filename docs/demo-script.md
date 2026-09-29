# Four-minute judge demo

**0:00 — Problem.** Open the landing page. Explain that voice is the front door to a structured profile, not a generic chatbot. Point to the demo-data label.

**0:20 — Voice and consent.** Select Beneficiary Mode, choose Hindi or English, read the AI disclosure, and consent. Tap the mic; if browser speech is unavailable, type the same answer. The Record Audio control demonstrates upload fallback; without Whisper installed it asks for browser voice or text.

**0:55 — Structured profile.** Answer the interview questions. Use “skip” for optional unknowns. Review the summary and confirm. Show that skills and interests remain separate.

**1:30 — Demo shortcut.** For repeatable timing, load “Sita · tailoring.” Explain that this is a synthetic persona, not a real beneficiary.

**1:50 — Explainable pathways.** Inspect top pathways, already-shared skills, skills to develop, eligibility verification status and local signal. Explain why no numeric AI score appears and why duration/fees are omitted.

**2:25 — Action and follow-up.** Choose a pathway and add a follow-up stage. This writes to the database.

**2:50 — Human support.** Request a counsellor and open the Counsellor page. Accept or resolve the queue item; inspect consented profile and follow-up.

**3:20 — Official dashboard.** Open Official Dashboard. Show data source labels, demand/capacity sample, map, funnel and the small-cell suppression note. Explain that values below five are hidden.

**3:50 — Privacy and roadmap.** Demonstrate session withdrawal. State plainly: no government integration, real district data, verified active catalogue, measured impact or production authentication is present. Future pilot work includes verified catalogue/demand data, assisted channels, real counsellor operations and security review.

## Backup

Use the sample persona buttons to bypass microphone/network recognition while still exercising the database-backed recommendation, selection, follow-up and dashboard flow. If the API is stopped, restart with the commands in README. Docker Compose seeds its own database at start.
