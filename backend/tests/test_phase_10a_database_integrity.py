import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal, engine


def test_phase_10a_sqlite_foreign_keys_are_enabled():
    if engine.dialect.name != "sqlite":
        pytest.skip("SQLite-specific foreign-key enforcement check")

    db = SessionLocal()
    try:
        enabled = db.execute(text("PRAGMA foreign_keys")).scalar()
        assert enabled == 1
    finally:
        db.close()


def test_phase_10a_rejects_orphan_recommendation_foreign_key():
    if engine.dialect.name != "sqlite":
        pytest.skip("SQLite-specific foreign-key enforcement check")

    db = SessionLocal()
    try:
        with pytest.raises(IntegrityError):
            db.execute(
                text(
                    """
                    INSERT INTO recommendations
                    (session_id, pathway_id, selected, explanation, created_at)
                    VALUES
                    ('phase10a-missing-session', 'phase10a-missing-pathway', 0, '{}', CURRENT_TIMESTAMP)
                    """
                )
            )
            db.commit()
    finally:
        db.rollback()
        db.close()
