from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import suppress
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def prepare_database_url(database_url: str) -> None:
    """Create private parent directories for local SQLite files without touching DB contents."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return
    filename = database_url[len(prefix) :].split("?", maxsplit=1)[0]
    if filename in {":memory:", ""}:
        return
    path = Path(filename).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with suppress(OSError):
        path.parent.chmod(0o700)


def create_database_engine(database_url: str) -> Engine:
    prepare_database_url(database_url)
    options: dict[str, object] = {"future": True}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False, "timeout": 5}
        if database_url.endswith((":memory:", "/:memory:")):
            options["poolclass"] = StaticPool
    engine = create_engine(database_url, **options)

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection: sqlite3.Connection, connection_record: object) -> None:
        del connection_record
        if not database_url.startswith("sqlite"):
            return
        # Use SQLAlchemy's begin hook for real SELECT snapshots; sqlite3 legacy mode skips SELECT transactions.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
        if not database_url.endswith((":memory:", "/:memory:")):
            url_path = database_url[len("sqlite:///") :].split("?", maxsplit=1)[0]
            database_path = Path(url_path).expanduser()
            if not database_path.is_absolute():
                database_path = Path.cwd() / database_path
            if database_path.exists():
                with suppress(OSError):
                    database_path.chmod(0o600)

    @event.listens_for(engine, "begin")
    def begin_sqlite_transaction(connection: Connection) -> None:
        if connection.dialect.name != "sqlite":
            return
        mode = connection.get_execution_options().get("sqlite_begin_mode", "DEFERRED")
        if mode not in {"DEFERRED", "IMMEDIATE"}:
            raise ValueError(f"Unsupported SQLite transaction mode: {mode}")
        connection.exec_driver_sql(f"BEGIN {mode}")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_session(factory: sessionmaker) -> Generator[Session]:
    with factory() as session:
        yield session
