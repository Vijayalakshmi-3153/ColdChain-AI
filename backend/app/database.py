"""
Database engine, session factory and FastAPI dependency.

Uses SQLAlchemy 2.x style with PostgreSQL (psycopg2 driver).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

settings = get_settings()

# PostgreSQL doesn't need check_same_thread (that's a SQLite thing).
engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,   # verify connections before using them
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def get_db():
    """FastAPI dependency that provides a scoped DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_connection() -> bool:
    """Return True if the database is reachable."""
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True