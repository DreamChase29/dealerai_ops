"""Database engine and session helpers."""

from collections.abc import Generator
from typing import Any

import structlog
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from dealerai_ops.core.config import get_settings

logger = structlog.get_logger(__name__)


def create_db_engine(database_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine for the configured database URL."""
    resolved_url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if resolved_url.startswith("sqlite") else {}
    engine = create_engine(resolved_url, pool_pre_ping=True, connect_args=connect_args)

    if resolved_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(
            dbapi_connection: Any,
            _connection_record: Any,
        ) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """Create a session factory bound to an engine."""
    return sessionmaker(
        bind=engine or create_db_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def get_session() -> Generator[Session, None, None]:
    """Yield a database session for FastAPI dependencies."""
    session_factory = create_session_factory()
    with session_factory() as session:
        yield session


def check_database_connection(database_url: str | None = None) -> bool:
    """Return whether the configured database accepts a simple query."""
    engine: Engine | None = None
    try:
        engine = create_db_engine(database_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("database_readiness_check_failed", error=str(exc))
        return False
    finally:
        if engine is not None:
            engine.dispose()
    return True
