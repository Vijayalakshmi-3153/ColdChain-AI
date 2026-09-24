"""
Database initialization script (migration-ready structure).

Usage (from the backend/ folder):

    python -m app.init_db

What it does:
1. Creates the target database if it does not exist (best effort).
2. Creates all tables defined by the SQLAlchemy models (Base.metadata).

For real schema migrations in later steps, use Alembic (see backend/alembic/).
"""

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from .config import get_settings
from .database import Base, engine
from . import models  # noqa: F401  (import so tables register on Base.metadata)

settings = get_settings()


def ensure_database() -> None:
    """Create the database if it is missing (requires a privileged user)."""
    admin_url = settings.sqlalchemy_database_url.rsplit("/", 1)[0] + "/postgres"
    try:
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": settings.db_name},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{settings.db_name}"'))
                print(f"[init_db] Created database '{settings.db_name}'.")
            else:
                print(f"[init_db] Database '{settings.db_name}' already exists.")
        admin_engine.dispose()
    except OperationalError as exc:
        # Non-fatal: the user may not have CREATE DATABASE rights.
        print(f"[init_db] Could not check/create database: {exc}")


def create_tables() -> None:
    """Create all tables defined by the models."""
    Base.metadata.create_all(bind=engine)
    print("[init_db] Tables created:", ", ".join(Base.metadata.tables))


def main() -> None:
    print(f"[init_db] Connecting to {settings.db_host}:{settings.db_port}/"
          f"{settings.db_name} as '{settings.db_user}' ...")
    ensure_database()
    create_tables()
    print("[init_db] Done.")


if __name__ == "__main__":
    main()