"""
Alembic environment configuration.

Reuses the SQLAlchemy metadata and database URL from the FastAPI app so
there is a single source of truth for configuration.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import app modules so Base.metadata contains all models.
from app.config import get_settings
from app.database import Base
from app import models  # noqa: F401

config = context.config

# Inject the database URL from environment variables (.env).
# Percent-encode for ConfigParser interpolation (passwords may contain '%' ).
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.sqlalchemy_database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()