# Alembic migration versions

Generated migration files are stored in this folder.

Create one from the `backend/` folder:

    alembic revision --autogenerate -m "initial schema"
    alembic upgrade head

Roll back with `alembic downgrade -1`.