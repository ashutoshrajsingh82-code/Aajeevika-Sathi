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
alembic upgrade head
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

The live interview path starts with consent, records each text or voice transcript in the backend, confirms the profile, then persists recommendations, centre matches, an action plan, a case and an initial follow-up. Selecting a pathway creates a counsellor handoff. The counsellor screen can update the case outcome, and aggregate analytics read those saved outcomes. Browser voice needs a supported browser and microphone permission. Whisper is optional; if transcription is unavailable, use browser voice or text. Only the explicitly selected synthetic persona offers a browser-local offline demo fallback; ordinary interview, selection, handoff and follow-up actions report an error when they cannot be saved to the API.

See [docs/end-to-end-flow.md](docs/end-to-end-flow.md) for the lifecycle, records, API sequence and manual verification procedure. The backend now uses versioned Alembic migrations; run `alembic upgrade head` before seeding or starting it. Local demo sign-ins are `admin` / `admin-demo-change-me` and `counsellor` / `counsellor-demo-change-me`. For production, set `DEMO_MODE=false`, a random `AUTH_SECRET`, and `AUTO_CREATE_SCHEMA=false`; create individual staff accounts with `python -m app.manage_users add-user --role admin --username <name>` and the corresponding `counsellor` command. The CLI prompts for passwords without echo. See the flow guide for password reset and account disabling.

The optional, disabled-by-default conversational interview and environment settings are described in [docs/ai-safety.md](docs/ai-safety.md). Set `AI_PROVIDER=ollama` with `AI_BASE_URL=http://localhost:11434/v1` and an `AI_MODEL` to use an OpenAI-compatible local Ollama server. When configured, the regular text and voice-transcript message flow validates structured profile extractions, retains each raw answer, and falls back to the guided interview if the provider is unavailable or returns invalid output.

## Environment

Copy `.env.example` to `.env` for local overrides. Defaults work without API keys.

| Variable | Use |
|---|---|
| `DATABASE_URL` | SQLAlchemy database URL; SQLite default, PostgreSQL-ready |
| `DEMO_MODE` | Labels API as demo (default true) |
| `FRONTEND_ORIGIN` | FastAPI CORS origin |
| `NEXT_PUBLIC_API_URL` | Browser-visible API base URL, default `http://localhost:8000` |
| `OPENAI_API_KEY` | Reserved provider configuration; actual LLM use depends on the configured AI provider |
| `BHASHINI_API_KEY`, `BHASHINI_API_URL` | Reserved adapter configuration; live Bhashini integration remains to be completed |
| `AUTH_SECRET` | Signing secret for the HTTP-only staff auth cookie; required and validated in non-demo mode |
| `AUTH_COOKIE_SECURE` | Secure-cookie flag; required true outside demo mode |
| `LOGIN_RATE_LIMIT`, `LOGIN_RATE_WINDOW_SECONDS` | Process-local login abuse limit; shared infrastructure is needed for multi-instance production |

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

Signed HTTP-only cookie authentication, staff role authorization, password hashing, token expiry, auth-version revocation, and login rate limiting are implemented and covered by backend tests. These controls are not a substitute for a production security assessment or deployment hardening. The current login limiter is process-local and protects the login endpoint only; multi-worker or multi-instance deployments need shared rate-limit state or an API gateway.

Verified government catalogue/district data, live Bhashini integration, real employment-outcome integration, retention enforcement, frontend automated tests/E2E coverage, and a production security/privacy assessment remain outstanding. No real beneficiary data should be entered into the demo. The repository does not claim production readiness solely from the automated test suite.
