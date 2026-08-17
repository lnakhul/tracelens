"""Async SQLite engine and session-factory helpers."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from tracelens.database.models import Base


def create_engine(database_path: Path) -> AsyncEngine:
    """Create an async engine for a local SQLite database file."""

    return create_async_engine(f"sqlite+aiosqlite:///{database_path.resolve()}")


async def initialize_database(engine: AsyncEngine) -> None:
    """Create the local schema when TraceLens starts for the first time."""

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create sessions used by trace persistence services."""

    return async_sessionmaker(engine, expire_on_commit=False)