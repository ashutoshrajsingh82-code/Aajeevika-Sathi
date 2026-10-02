import sys
from pathlib import Path

BACKEND=Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0,str(BACKEND))


import pytest


@pytest.fixture(autouse=True)
def reset_login_rate_limiter():
    """Keep process-local auth limiter state isolated between tests."""
    from app.main import login_rate_limiter

    login_rate_limiter._events.clear()
    yield
    login_rate_limiter._events.clear()
