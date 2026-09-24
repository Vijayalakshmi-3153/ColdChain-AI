"""
Pytest configuration for ColdChain AI backend tests.

Uses an in-memory SQLite database so tests never touch the real
PostgreSQL data, and starts FastAPI WITHOUT the lifespan (no broker /
DB side effects during unit tests).
"""

import pathlib
import sys

# Make `app.*` importable regardless of where pytest is launched from.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (register tables)
from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def db_session():
    """Fresh in-memory SQLite session with the full schema created."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    yield session
    session.close()


@pytest.fixture()
def client(db_session):
    """FastAPI test client wired to the in-memory database."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # NOTE: no `with` block - TestClient only runs the lifespan (MQTT/DB
    # startup) when used as a context manager, which we don't want here.
    yield TestClient(app)
    app.dependency_overrides.clear()