"""Database connection management."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pgh_ticket.config import db
from pgh_ticket.models import Base


class Database:
    """Async database wrapper: engine + session factory."""

    def __init__(
        self,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.engine = engine
        self.session_factory = session_factory

    async def init(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            # Migration: add ticket_key if missing
            rows = await conn.execute(
                text("SELECT 1 FROM pragma_table_info('tickets') WHERE name='ticket_key'")
            )
            if not rows.scalar():
                await conn.execute(
                    text("ALTER TABLE tickets ADD COLUMN ticket_key VARCHAR NOT NULL DEFAULT ''")
                )
            # Migration: recreate locations table if it has old schema (ticket_number PK)
            old_loc = await conn.execute(
                text("SELECT 1 FROM pragma_table_info('locations') WHERE name='ticket_number'")
            )
            if old_loc.scalar():
                await conn.execute(text("DROP TABLE locations"))
                await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_factory() as s:
            yield s


def create_database(path: str | None = None) -> Database:
    db_path = path or db.settings.db_path
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return Database(engine=engine, session_factory=factory)
