"""Shared fixtures.

Two tiers of tests:
- Default (`pytest`): fast and isolated — external calls are mocked, database
  sessions are fakes. Safe to run anywhere, anytime.
- Live (`pytest -m live`): read-only checks against the real database and the
  deployed Railway service. They never write — sessions are rolled back.
"""
import os

import pytest
from dotenv import load_dotenv

load_dotenv()  # before any app import so env vars are present


@pytest.fixture(scope="session")
def db():
    """Session against the real database. Read-only by convention:
    tests must roll back, never commit."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(os.getenv("DATABASE_URL"), pool_pre_ping=True)
    session = sessionmaker(bind=engine)()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture()
def fake_db(mocker):
    """Stand-in Session for tests that must not touch the real database.
    Queries return empty results; add/commit are absorbed silently."""
    db = mocker.MagicMock()
    db.query.return_value.filter_by.return_value.all.return_value = []
    db.query.return_value.filter_by.return_value.first.return_value = None
    return db
