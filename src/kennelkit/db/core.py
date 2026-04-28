"""
Database core — engine, session, and Base class.

The engine is configured at runtime via configure() rather than at import time.
This lets the framework be imported without a database connection, and lets
test suites use a different DB.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Parent class for all SQLAlchemy models in kennelkit and modules."""


class _DBState:
    """Singleton holding the configured engine and session factory."""

    def __init__(self) -> None:
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None


_state = _DBState()


def configure(database_url: str, *, echo: bool = False) -> None:
    """
    Initialize the engine and session factory.

    Args:
        database_url: SQLAlchemy URL, e.g.
            'postgresql+asyncpg://user:pass@host/dbname'
            'postgresql://user:pass@host/dbname' (auto-upgraded to asyncpg)
        echo: If True, SQLAlchemy logs every statement. For debugging only.
    """
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )
    elif not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError(
            f"kennelkit currently only supports Postgres via asyncpg. "
            f"Got: {database_url[:30]!r}..."
        )

    _state.engine = create_async_engine(database_url, echo=echo)
    _state.session_factory = async_sessionmaker(
        _state.engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def get_engine() -> AsyncEngine:
    """Return the configured engine. Raises if configure() wasn't called."""
    if _state.engine is None:
        raise RuntimeError(
            "kennelkit.db is not configured. Call kennelkit.db.configure(url) first."
        )
    return _state.engine


def session() -> AsyncSession:
    """Return a new AsyncSession. Use as `async with session() as s:`."""
    if _state.session_factory is None:
        raise RuntimeError(
            "kennelkit.db is not configured. Call kennelkit.db.configure(url) first."
        )
    return _state.session_factory()


async def shutdown() -> None:
    """Dispose of the engine. Call on bot shutdown."""
    if _state.engine is not None:
        await _state.engine.dispose()
        _state.engine = None
        _state.session_factory = None