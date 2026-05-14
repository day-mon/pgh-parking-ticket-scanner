"""Async database engine and session factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator

from platformdirs import user_data_dir
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pgh_ticket.models import Base

_DIR = Path(user_data_dir("pgh-ticket", ensure_exists=True))
_DEFAULT_DB = str(_DIR / "tickets.db")


@dataclass(slots=True)
class Database:
    """Minimal async database wrapper: engine + session factory."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]

    async def init(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_factory() as s:
            yield s


def create_database(path: str | None = None) -> Database:
    db_path = path or _DEFAULT_DB
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return Database(engine=engine, session_factory=factory)
