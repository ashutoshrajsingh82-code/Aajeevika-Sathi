# End-to-end beneficiary flow

This prototype now stores interview evidence, recommendations, case status, counselling handoff, follow-up and outcome in the FastAPI database. The API remains the source of truth for saved records. The browser's synthetic persona fallback is explicitly marked as offline demo data.

## Lifecycle

| State | Entered when | Persistent evidence |
| --- | --- | --- |
| `CONSENT` | A session is created and consent is requested | Session start audit |
| `INTERVIEW` | Consent is granted | Consent answer, timestamp and transition audit |
| `PROFILE_REVIEW` | All interview slots are answered or skipped | Raw and normalized answers; profile completion audit |
| `RECOMMENDATION` | The beneficiary confirms and completes the profile | Completion timestamp, recommendations, action plan, case and initial follow-up |
| `PATHWAY_SELECTED` | A recommended pathway is chosen | Selected recommendation and transition audit |
| `COUNSELLOR_HANDOFF` | The selection creates a counsellor task, or the beneficiary asks for support | Handoff row and transition audit |
| `FOLLOW_UP` | A follow-up is completed or the counsellor records training started | Follow-up update and transition audit |
| `COMPLETED` | A counsellor records employment or self-employment | Outcome and final transition audit |

Skipped interview slots are recorded in the profile's `skipped_slots`; required matching details (district and at least one skill or interest) are validated before recommendation generation. This is prototype validation, not an eligibility determination.

## API sequence

1. `POST /api/v1/interview/session` creates a consent-pending session.
2. `POST /api/v1/interview/session/{id}/message` handles consent and every answer. `input_method` is `text`, `browser_voice`, or `server_transcription`.
3. Browser speech and Whisper transcription send their transcript through that same message route. Audio is processed in memory and is not persisted.
4. After profile confirmation, `POST /api/v1/interview/session/{id}/complete` validates and atomically saves the completion timestamp, recommendation snapshots (including centre match and decision evidence), action plan, case, initial follow-up, and audit event.
5. `GET /api/v1/case/{id}` returns the saved case, profile state, recommendations, handoffs and follow-ups.
6. `POST /api/v1/recommendations/select` saves selection and creates a counsellor handoff and follow-up.
7. The livelihood agent is an authenticated staff action: `POST /api/v1/agent/livelihood/{id}/run` starts a bounded planning run using only persisted catalogue/knowledge records. `GET /api/v1/agent/livelihood/{id}/status` returns the latest persisted agent run for refresh/polling; `GET /api/v1/agent/livelihood/session/{agent_session_id}` returns the persisted run by ID. The API deliberately does not expose arbitrary tool execution.
8. Counsellors use `/api/v1/handoff/queue`, `/api/v1/handoff/{id}`, `/api/v1/followups`, and `/api/v1/followups/{id}`. `PATCH /api/v1/case/{id}/outcome` records an outcome.
9. `/api/v1/admin/analytics` derives funnel and outcome counts from database records and suppresses small groups.
10. `DELETE /api/v1/interview/session/{id}` removes answers, case, recommendations, handoffs, follow-ups, agent sessions, and session data.

## Persistence

`InterviewSession` stores the current state, consent, profile, completion timestamp, last activity, completion percentage and interview version. `InterviewAnswer` stores the original text, normalized value, question, language and input method. `RecommendationRecord.explanation` includes a snapshot of the complete rendered recommendation to keep centre matching and explanations available after refresh. `BeneficiaryCase` stores selected pathway, case status, action plan and counsellor outcome. `AuthUser` stores a unique staff username, salted PBKDF2 password hash, role, active status, token version and timestamps. `AuditLog` captures lifecycle and task updates.

Schema changes are versioned in Alembic migrations. Run `alembic upgrade head` from `backend` before starting the API. The initial baseline recognizes an existing database with a `sessions` table; the lifecycle revision adds the new columns and tables without dropping beneficiary data. `AUTO_CREATE_SCHEMA=true` remains enabled by default only for local demo mode. Set it to `false` in production so startup cannot silently create an incomplete schema.

## Demo versus real data

`POST /api/v1/demo/profile` is an explicit synthetic-persona endpoint. Seeded pathways, centres and demand are labelled sample data and must be verified by a counsellor. The browser-local fallback exists only for the explicitly selected synthetic demo persona; ordinary interview, selection and follow-up actions report backend errors if they cannot be saved.

## Staff access

Counsellor and admin pages require sign-in. Staff routes use role checks; the browser receives a signed, HTTP-only, same-site cookie. `POST /api/v1/auth/login`, `GET /api/v1/auth/me` and `POST /api/v1/auth/logout` manage the cookie. Admin analytics require the admin role; counsellor queues and case updates accept either staff role. Each account is stored with a salted PBKDF2 password hash, role, active flag and token version. Production operators create individual accounts through the interactive CLI, can reset passwords or disable accounts, and those actions revoke outstanding cookies. Set `DEMO_MODE=false`, `AUTO_CREATE_SCHEMA=false`, and a random `AUTH_SECRET` of at least 32 characters; use HTTPS so cookies are secure. Local demo credentials are `admin` / `admin-demo-change-me` and `counsellor` / `counsellor-demo-change-me`.

Create production staff users after migrations with `python -m app.manage_users add-user --role admin --username "your-admin-name"` and repeat with `--role counsellor`. Under Compose, prefix the command with `docker compose exec api`. The CLI prompts for passwords without echo and requires 12 or more characters. To rotate or disable users, use `set-password` or `disable-user` with `--username "your-user-name"`.

## Manual check

Run the backend from `backend` using `uvicorn app.main:app --reload --port 8000`, then run the frontend from `frontend` using `npm run dev`. Open `/beneficiary`, consent, answer each prompt (use the microphone or text), confirm the profile, inspect recommendations, select one, then open `/counsellor`. Accept the task, record an outcome, and check `/admin`. All saved actions use the backend API.
