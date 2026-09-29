import os

DATABASE_URL=os.getenv("DATABASE_URL", "sqlite:///./aajeevika.db")
DEMO_MODE=os.getenv("DEMO_MODE", "true").lower()=="true"
FRONTEND_ORIGIN=os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
WEIGHTS={"interest":.30,"skills":.25,"demand":.20,"feasibility":.15,"preference":.10}
