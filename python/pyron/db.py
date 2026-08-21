"""SQLModel + Alembic helpers.

The framework does not own your database. These helpers give a one-file
session factory and CLI-friendly Alembic wrappers so `pyron db …` works
the same in every generated project.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

DEFAULT_URL = "sqlite:///./pyron.db"

def mongo_client(*args, **kwargs):
    from pyron.mongo import mongo_client as _mongo

    return _mongo(*args, **kwargs)


def redis_client(*args, **kwargs):
    from pyron.cache import redis_client as _redis

    return _redis(*args, **kwargs)


def database_url(explicit: str | None = None) -> str:
    return explicit or os.environ.get("DATABASE_URL") or DEFAULT_URL


def create_engine(url: str | None = None, **kwargs: Any):
    from sqlmodel import create_engine as _create

    url = database_url(url)
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        kwargs.setdefault("connect_args", connect_args)
    return _create(url, **kwargs)


def init_db(engine: Any, metadata: Any | None = None) -> None:
    from sqlmodel import SQLModel

    (metadata or SQLModel.metadata).create_all(engine)


@contextmanager
def session_scope(engine: Any) -> Generator[Any, None, None]:
    from sqlmodel import Session

    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session(engine: Any):
    """FastAPI-style dependency: `session: Session = Depends(get_session)`."""

    def _dep():
        from sqlmodel import Session

        with Session(engine) as session:
            yield session

    return _dep


def write_alembic_ini(root: Path, script_location: str = "alembic", url: str | None = None) -> Path:
    url = database_url(url)
    path = root / "alembic.ini"
    path.write_text(
        f"""[alembic]
script_location = {script_location}
prepend_sys_path = .
sqlalchemy.url = {url}

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
""",
        encoding="utf-8",
    )
    return path


def write_alembic_env(alembic_dir: Path) -> None:
    alembic_dir.mkdir(parents=True, exist_ok=True)
    (alembic_dir / "script.py.mako").write_text(
        '''"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
''',
        encoding="utf-8",
    )
    versions = alembic_dir / "versions"
    versions.mkdir(exist_ok=True)
    (versions / ".gitkeep").write_text("", encoding="utf-8")
    (alembic_dir / "env.py").write_text(
        '''from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = os.environ.get("DATABASE_URL")
if url:
    config.set_main_option("sqlalchemy.url", url)

try:
    from sqlmodel import SQLModel
    from app import models  # noqa: F401
    target_metadata = SQLModel.metadata
except Exception:
    target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
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
''',
        encoding="utf-8",
    )


def alembic_command(root: Path, *args: str) -> int:
    import subprocess
    import sys

    ini = root / "alembic.ini"
    cmd = [sys.executable, "-m", "alembic", "-c", str(ini), *args]
    return subprocess.call(cmd, cwd=str(root))
