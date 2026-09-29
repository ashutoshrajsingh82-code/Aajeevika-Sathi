# Aajeevika Sathi

**From your voice to your livelihood.** A PM-AJAY livelihood pathway prototype focused on accessible voice-led intake, explainable recommendations and counsellor support.

> **Demo disclosure:** This repository demonstrates a working software flow. It is not connected to PM-AJAY or any government service. Pathways, training centres and district demand/capacity are simulated. There are no real beneficiary outcomes, employment impact or measured model accuracy.

## Run locally on Windows

### Option A: Docker (recommended)

Install Docker Desktop, then in PowerShell:

```powershell
cd C:\Users\ASHUTOSH\SIH97
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000). API health: [http://localhost:8000/health](http://localhost:8000/health). Stop with `Ctrl+C`; run `docker compose down` to stop containers. The named `dbdata` volume retains demo database data.

### Option B: Run services separately

Terminal 1 — backend:

```powershell
cd C:\Users\ASHUTOSH\SIH97\backend
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python seed.py
uvicorn app.main:app --reload --port 8000
```

Terminal 2 — frontend:

```powershell
cd C:\Users\ASHUTOSH\SIH97\frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The separately-run API defaults to a local SQLite file in `backend`.

## Validate

```powershell
cd C:\Users\ASHUTOSH\SIH97\backend
py -m pytest tests -q
py -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
cd ..\frontend
npm run lint
npm run build
```

## Demo flow

Landing → Guided Demo → Beneficiary → load synthetic Sita/Rahul/Aman → inspect profile and pathway reasoning → choose a pathway → add a follow-up → request counsellor → inspect Counsellor queue → Official Dashboard → withdraw/delete session.

The live interview path starts with disclosure and consent, asks one fixed question per turn, supports browser voice and text, confirms the profile, then returns pathways. Browser voice needs a supported browser and microphone permission. Whisper is optional; with no local model, audio upload falls back to browser voice/text. After the PWA shell and route assets have been loaded once, synthetic persona recommendations, pathway selection, handoff and follow-up can use browser-local storage while the API is offline. Browser-local demo events are clearly separated from database records.

## Environment

Copy `.env.example` to `.env` for local overrides. Defaults work without API keys.

| Variable | Use |
|---|---|
| `DATABASE_URL` | SQLAlchemy database URL; SQLite default, PostgreSQL-ready |
| `DEMO_MODE` | Labels API as demo (default true) |
| `FRONTEND_ORIGIN` | FastAPI CORS origin |
| `NEXT_PUBLIC_API_URL` | Browser-visible API base URL, default `http://localhost:8000` |
| `OPENAI_API_KEY` | Reserved; no LLM call is currently made |
| `BHASHINI_API_KEY`, `BHASHINI_API_URL` | Reserved adapter configuration; endpoint-specific integration remains to be implemented |
| `JWT_SECRET` | Reserved for production authentication; current role views are demo-only |

## Repository

```text
backend/app/       FastAPI, SQLAlchemy models, interview, speech, recommender
backend/tests/     deterministic engine tests
backend/seed.py    idempotent sample pathway/centre/demand seeding
frontend/app/      Next.js landing, beneficiary, counsellor, admin and demo pages
frontend/components/ shared motion and Leaflet map
docs/              architecture, safety, privacy, evaluation, demo and roadmap
docker-compose.yml local two-service setup with persistent SQLite volume
```

## Data reality

- Pathway names in the demo seed are illustrative concepts, not verified active NSQF qualifications.
- Centre locations and all contact/accessibility fields are sample placeholders.
- District-sector demand labels are synthetic neutral samples, not PLFS/NCS/District Skill Plan statistics.
- Capacity values are placeholder zeros, not reported training capacity.
- No beneficiary or outcome records are pre-seeded; counts update from demo interactions and are suppressed below five.
- Course eligibility, duration, cost, batch dates and credit links are intentionally omitted until verified from active official sources.

See [architecture](docs/architecture.md), [AI safety](docs/ai-safety.md), [privacy](docs/privacy.md), [recommendations](docs/recommendation-engine.md), [evaluation](docs/evaluation.md), [demo script](docs/demo-script.md) and [roadmap](docs/roadmap.md).

## Limitations before real use

Production JWT authentication and role authorization, privacy/security assessment, retention enforcement, deployment hardening, verified catalogue and district data, and live Bhashini integration are not implemented. No real user data should be entered. See documentation for details.
