from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from fixlog.config import get_settings

logger = logging.getLogger(__name__)


def create_fixlog_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine_kwargs: dict[str, object] = {
        "future": True,
        "connect_args": connect_args,
    }
    if database_url == "sqlite:///:memory:":
        engine_kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, **engine_kwargs)
    event.listen(engine, "connect", _configure_sqlite)
    return engine


def _configure_sqlite(dbapi_connection: object, connection_record: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

    try:
        import sqlite_vec
    except ModuleNotFoundError:
        logger.info("sqlite-vec package not installed; embedding column remains inert")
        return

    try:
        sqlite_vec.load(dbapi_connection)
    except Exception as exc:  # pragma: no cover - depends on local extension support
        logger.info("sqlite-vec extension not loaded: %s", exc)


engine = create_fixlog_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all_for_tests(connection: Connection) -> None:
    from fixlog.db.models import Base

    Base.metadata.create_all(bind=connection)
