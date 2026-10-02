import os

DATABASE_URL=os.getenv("DATABASE_URL", "sqlite:///./aajeevika.db")
DEMO_MODE=os.getenv("DEMO_MODE", "true").lower()=="true"
AUTO_CREATE_SCHEMA=os.getenv("AUTO_CREATE_SCHEMA", "true" if DEMO_MODE else "false").lower()=="true"
FRONTEND_ORIGIN=os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
AUTH_SECRET=os.getenv("AUTH_SECRET", "local-demo-signing-key-change-before-deploy")
AUTH_COOKIE_SECURE=os.getenv("AUTH_COOKIE_SECURE", "false" if DEMO_MODE else "true").lower()=="true"
AUTH_COOKIE_NAME="aajeevika_access"
AUTH_REFRESH_COOKIE_NAME="aajeevika_refresh"
AUTH_COOKIE_HOURS=int(os.getenv("AUTH_COOKIE_HOURS", "8"))
AUTH_REFRESH_COOKIE_HOURS=int(os.getenv("AUTH_REFRESH_COOKIE_HOURS", "168"))
DEMO_ADMIN_USERNAME=os.getenv("DEMO_ADMIN_USERNAME","admin")
DEMO_ADMIN_PASSWORD=os.getenv("DEMO_ADMIN_PASSWORD","admin-demo-change-me")
DEMO_COUNSELLOR_USERNAME=os.getenv("DEMO_COUNSELLOR_USERNAME","counsellor")
DEMO_COUNSELLOR_PASSWORD=os.getenv("DEMO_COUNSELLOR_PASSWORD","counsellor-demo-change-me")
if not DEMO_MODE:
    if DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("Production mode requires a non-SQLite DATABASE_URL")
    if not FRONTEND_ORIGIN.startswith("https://"):
        raise RuntimeError("Production FRONTEND_ORIGIN must use HTTPS")
    if not os.getenv("AUTH_SECRET"):raise RuntimeError("Production auth configuration missing: AUTH_SECRET")
    AUTH_SECRET=os.environ["AUTH_SECRET"]
    if len(AUTH_SECRET)<32:raise RuntimeError("AUTH_SECRET must contain at least 32 characters")
    if not AUTH_COOKIE_SECURE:raise RuntimeError("AUTH_COOKIE_SECURE must be true outside demo mode")
    if AUTH_SECRET=="local-demo-signing-key-change-before-deploy" or "replace-with-" in AUTH_SECRET.lower():raise RuntimeError("Replace the example signing secret before production")
WEIGHTS={"interest":.30,"skills":.25,"demand":.20,"feasibility":.15,"preference":.10}
def _followup_days():
    raw=os.getenv("FOLLOWUP_INTERVAL_DAYS","7,30,90")
    try:days=tuple(sorted({int(item.strip()) for item in raw.split(",") if item.strip()}))
    except ValueError as exc:raise RuntimeError("FOLLOWUP_INTERVAL_DAYS must be a comma-separated list of integers") from exc
    if not days or any(day<1 or day>730 for day in days):raise RuntimeError("FOLLOWUP_INTERVAL_DAYS values must be between 1 and 730 days")
    return days
FOLLOWUP_INTERVAL_DAYS=_followup_days()

LOGIN_RATE_LIMIT=int(os.getenv("LOGIN_RATE_LIMIT","10"))
LOGIN_RATE_WINDOW_SECONDS=int(os.getenv("LOGIN_RATE_WINDOW_SECONDS","60"))
REFRESH_RATE_LIMIT=int(os.getenv("REFRESH_RATE_LIMIT","20"))
REFRESH_RATE_WINDOW_SECONDS=int(os.getenv("REFRESH_RATE_WINDOW_SECONDS","60"))

if AUTH_COOKIE_HOURS < 1 or AUTH_COOKIE_HOURS > 24:
    raise RuntimeError("AUTH_COOKIE_HOURS must be between 1 and 24")
if AUTH_REFRESH_COOKIE_HOURS < 1 or AUTH_REFRESH_COOKIE_HOURS > 720:
    raise RuntimeError("AUTH_REFRESH_COOKIE_HOURS must be between 1 and 720")
if LOGIN_RATE_LIMIT < 1 or LOGIN_RATE_WINDOW_SECONDS < 1:
    raise RuntimeError("Login rate-limit settings must be positive")
if REFRESH_RATE_LIMIT < 1 or REFRESH_RATE_WINDOW_SECONDS < 1:
    raise RuntimeError("Refresh rate-limit settings must be positive")
