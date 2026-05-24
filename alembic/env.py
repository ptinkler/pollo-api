"""Alembic environment configuration.

Uses the same DB_PATH and models as the application so that
`alembic revision --autogenerate` and `alembic upgrade head`
always target the correct database.
"""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from img2vid.common.metadata import Base

# Alembic Config object
config = context.config

# Use sqlalchemy.url if already set (e.g. by tests or CLI override),
# otherwise derive from the app's DB_PATH config.
if not config.get_main_option("sqlalchemy.url") or \
   config.get_main_option("sqlalchemy.url") == "sqlite:///placeholder":
    from img2vid.common.config import DB_PATH
    config.set_main_option("sqlalchemy.url", f"sqlite:///{DB_PATH}")

# Set up Python logging from the .ini file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point Alembic at our ORM metadata for autogenerate support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without connecting)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite ALTER TABLE
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (with a live connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # required for SQLite ALTER TABLE
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
