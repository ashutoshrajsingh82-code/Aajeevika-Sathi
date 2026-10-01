import os

DATABASE_URL=os.getenv("DATABASE_URL", "sqlite:///./aajeevika.db")
DEMO_MODE=os.getenv("DEMO_MODE", "true").lower()=="true"
AUTO_CREATE_SCHEMA=os.getenv("AUTO_CREATE_SCHEMA", "true" if DEMO_MODE else "false").lower()=="true"
FRONTEND_ORIGIN=os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
AUTH_SECRET=os.getenv("AUTH_SECRET", "local-demo-signing-key-change-before-deploy")
AUTH_COOKIE_SECURE=os.getenv("AUTH_COOKIE_SECURE", "false" if DEMO_MODE else "true").lower()=="true"
AUTH_COOKIE_NAME="aajeevika_access"
AUTH_COOKIE_HOURS=int(os.getenv("AUTH_COOKIE_HOURS", "8"))
DEMO_ADMIN_USERNAME=os.getenv("DEMO_ADMIN_USERNAME","admin")
DEMO_ADMIN_PASSWORD=os.getenv("DEMO_ADMIN_PASSWORD","admin-demo-change-me")
DEMO_COUNSELLOR_USERNAME=os.getenv("DEMO_COUNSELLOR_USERNAME","counsellor")
DEMO_COUNSELLOR_PASSWORD=os.getenv("DEMO_COUNSELLOR_PASSWORD","counsellor-demo-change-me")
if not DEMO_MODE:
    if not os.getenv("AUTH_SECRET"):raise RuntimeError("Production auth configuration missing: AUTH_SECRET")
    AUTH_SECRET=os.environ["AUTH_SECRET"]
    if len(AUTH_SECRET)<32:raise RuntimeError("AUTH_SECRET must contain at least 32 characters")
    if not AUTH_COOKIE_SECURE:raise RuntimeError("AUTH_COOKIE_SECURE must be true outside demo mode")
    if AUTH_SECRET=="local-demo-signing-key-change-before-deploy" or "replace-with-" in AUTH_SECRET.lower():raise RuntimeError("Replace the example signing secret before production")
WEIGHTS={"interest":.30,"skills":.25,"demand":.20,"feasibility":.15,"preference":.10}
