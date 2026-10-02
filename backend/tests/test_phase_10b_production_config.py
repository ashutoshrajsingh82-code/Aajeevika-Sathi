import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _import_config(env):
    merged = os.environ.copy()
    merged.update(env)
    return subprocess.run(
        [sys.executable, "-c", "import app.config"],
        cwd=BACKEND,
        env=merged,
        capture_output=True,
        text=True,
    )


def test_phase_10b_production_requires_strong_auth_configuration():
    result = _import_config({
        "DEMO_MODE": "false",
        "DATABASE_URL": "postgresql://example",
        "FRONTEND_ORIGIN": "https://example.gov",
        "AUTH_SECRET": "short",
        "AUTH_COOKIE_SECURE": "true",
    })
    assert result.returncode != 0
    assert "at least 32 characters" in result.stderr


def test_phase_10b_production_rejects_sqlite_and_http_frontend():
    result = _import_config({
        "DEMO_MODE": "false",
        "DATABASE_URL": "sqlite:///./production.db",
        "FRONTEND_ORIGIN": "http://example.gov",
        "AUTH_SECRET": "x" * 64,
        "AUTH_COOKIE_SECURE": "true",
    })
    assert result.returncode != 0
    assert "non-SQLite DATABASE_URL" in result.stderr


def test_phase_10b_production_requires_https_frontend():
    result = _import_config({
        "DEMO_MODE": "false",
        "DATABASE_URL": "postgresql://example",
        "FRONTEND_ORIGIN": "http://example.gov",
        "AUTH_SECRET": "x" * 64,
        "AUTH_COOKIE_SECURE": "true",
    })
    assert result.returncode != 0
    assert "must use HTTPS" in result.stderr
