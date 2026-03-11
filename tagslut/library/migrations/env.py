from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from tagslut.library import DEFAULT_LIBRARY_DB_URL, resolve_library_db_url
from tagslut.library.models import Base
from tagslut.utils.config import get_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_db_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return resolve_library_db_url(configured)
    config_value = get_config().get("library.db_url", DEFAULT_LIBRARY_DB_URL)
    return resolve_library_db_url(str(config_value))


def run_migrations_offline() -> None:
    context.configure(
        url=_get_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_get_db_url(), future=True)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
