"""Database connection management."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

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

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_factory() as s:
            yield s


def create_database(url: str | None = None) -> Database:
    uri = url or db.settings.database_url
    engine = create_async_engine(uri, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return Database(engine=engine, session_factory=factory)
