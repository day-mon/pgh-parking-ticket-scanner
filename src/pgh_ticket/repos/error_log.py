"""Error log repository."""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pgh_ticket.models import ErrorLog


class ErrorLogRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session: AsyncSession = session

    async def log(self, *, number: str, command: str, exc: Exception) -> ErrorLog:
        error_type = type(exc).__name__
        message = str(exc)[:500]
        now = datetime.datetime.now(datetime.UTC).isoformat()

        stmt = select(ErrorLog).where(
            ErrorLog.number == number,
            ErrorLog.command == command,
            ErrorLog.error_type == error_type,
            ErrorLog.resolved.is_(False),
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.last_seen = now
            existing.retries += 1
            await self.session.commit()
            return existing

        obj = ErrorLog(
            number=number,
            command=command,
            error_type=error_type,
            message=message,
            first_seen=now,
            last_seen=now,
        )
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def list_unresolved(self) -> Sequence[ErrorLog]:
        result = await self.session.execute(
            select(ErrorLog).where(ErrorLog.resolved.is_(False)).order_by(ErrorLog.last_seen.desc())
        )
        return result.scalars().all()

    async def stats(self) -> dict[str, Any]:
        total = await self.session.execute(select(func.count(ErrorLog.id)))
        unresolved = await self.session.execute(
            select(func.count(ErrorLog.id)).where(ErrorLog.resolved.is_(False))
        )
        by_type = await self.session.execute(
            select(ErrorLog.error_type, func.count(ErrorLog.id))
            .group_by(ErrorLog.error_type)
            .order_by(func.count(ErrorLog.id).desc())
        )
        return {
            "total": total.scalar_one() or 0,
            "unresolved": unresolved.scalar_one() or 0,
            "by_type": {row[0]: row[1] for row in by_type.all()},
        }

    async def clear(self) -> int:
        count = await self.session.scalar(select(func.count(ErrorLog.id)))
        await self.session.execute(delete(ErrorLog))
        await self.session.commit()
        return count or 0

    async def mark_resolved(self, number: str, command: str) -> None:
        await self.session.execute(
            delete(ErrorLog).where(ErrorLog.number == number, ErrorLog.command == command)
        )
        await self.session.commit()
