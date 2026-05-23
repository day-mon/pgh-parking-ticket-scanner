"""Scan repository."""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pgh_ticket.models import Scan


class ScanRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session: AsyncSession = session

    async def create(
        self,
        *,
        range_start: int,
        range_end: int,
        until_date: str,
        tickets_found: int,
        errors: int,
        duration_s: float,
    ) -> Scan:
        now = datetime.datetime.now(datetime.UTC).isoformat()
        scan = Scan(
            range_start=range_start,
            range_end=range_end,
            until_date=until_date,
            tickets_found=tickets_found,
            errors=errors,
            duration_s=duration_s,
            scanned_at=now,
        )
        self.session.add(scan)
        await self.session.commit()
        await self.session.refresh(scan)
        return scan

    async def recent(self, limit: int = 10) -> Sequence[Scan]:
        result = await self.session.execute(
            select(Scan).order_by(Scan.scanned_at.desc()).limit(limit)
        )
        return result.scalars().all()
