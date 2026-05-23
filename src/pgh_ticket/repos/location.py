"""Location repository."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pgh_ticket.models import Location


class LocationRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, raw_location: str) -> Location | None:
        return await self._session.get(Location, raw_location)

    async def list_missing(self, limit: int | None = None) -> list[Location]:
        stmt = (
            select(Location)
            .where(Location.latitude.is_(None))
            .order_by(Location.raw_location)
        )
        if limit:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(self, data: dict[str, object]) -> None:
        loc = await self._session.get(Location, data["raw_location"])
        if loc:
            for key, value in data.items():
                if key != "raw_location" and hasattr(loc, key):
                    setattr(loc, key, value)
        else:
            loc = Location(**data)
            self._session.add(loc)
        await self._session.flush()

    async def bulk_upsert(self, items: list[dict[str, object]]) -> int:
        for data in items:
            await self.upsert(data)
        return len(items)

    async def get_existing_locations(self) -> set[str]:
        """Return set of all already-geocoded location strings."""
        stmt = select(Location.raw_location).where(Location.latitude.is_not(None))
        result = await self._session.execute(stmt)
        return {row[0] for row in result.all()}

    async def count_tickets_by_location(self) -> dict[str, int]:
        """Return count of tickets per distinct location string."""
        from pgh_ticket.models import Ticket

        stmt = (
            select(Ticket.location, func.count())
            .where(Ticket.location != "", Ticket.location.is_not(None))
            .group_by(Ticket.location)
        )
        result = await self._session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}
