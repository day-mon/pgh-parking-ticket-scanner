"""Ticket repository."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pgh_ticket.models import Ticket


class TicketRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session: AsyncSession = session

    async def get(self, number: str) -> Ticket | None:
        return await self.session.get(Ticket, number)

    async def get_numbers_in_range(self, lo: int, hi: int) -> set[int]:
        stmt = select(Ticket.ticket_number).where(
            Ticket.ticket_number >= str(lo),
            Ticket.ticket_number <= str(hi),
        )
        result = await self.session.execute(stmt)
        return {int(row[0]) for row in result.all()}

    async def get_all_numbers(self) -> set[str]:
        result = await self.session.execute(select(Ticket.ticket_number))
        return {row[0] for row in result.all()}

    async def list_tickets(
        self,
        *,
        state: str | None = None,
        status: str | None = None,
        date_from: str | date | None = None,
        date_to: str | date | None = None,
        limit: int = 50,
        sort: str = "date",
    ) -> Sequence[Ticket]:
        stmt = select(Ticket)
        if state:
            stmt = stmt.where(Ticket.state == state.upper())
        if status:
            stmt = stmt.where(Ticket.status == status.lower())
        if date_from:
            # accepts str "YYYY-MM-DD" or date object
            from_val = date_from if isinstance(date_from, date) else date.fromisoformat(date_from)
            stmt = stmt.where(Ticket.issue_date >= from_val)
        if date_to:
            to_val = date_to if isinstance(date_to, date) else date.fromisoformat(date_to)
            stmt = stmt.where(Ticket.issue_date <= to_val)

        if sort == "updated":
            stmt = stmt.order_by(Ticket.updated_at.desc())
        elif sort == "number":
            stmt = stmt.order_by(Ticket.ticket_number.desc())
        else:
            stmt = stmt.order_by(Ticket.issue_date.desc(), Ticket.ticket_number.desc())

        stmt = stmt.limit(limit)
        return (await self.session.execute(stmt)).scalars().all()

    async def list_missing_keys(self, limit: int | None = None) -> Sequence[Ticket]:
        stmt = select(Ticket).where(Ticket.ticket_key == "").order_by(Ticket.ticket_number)
        if limit:
            stmt = stmt.limit(limit)
        return (await self.session.execute(stmt)).scalars().all()

    async def list_missing_details(self, limit: int | None = None) -> Sequence[Ticket]:
        stmt = (
            select(Ticket)
            .where(Ticket.ticket_key != "", Ticket.location == "")
            .order_by(Ticket.ticket_number)
        )
        if limit:
            stmt = stmt.limit(limit)
        return (await self.session.execute(stmt)).scalars().all()

    async def bulk_upsert(self, data: list[dict[str, Any]], batch_size: int = 500) -> int:
        """Merge tickets in batches. Returns count merged."""
        total = 0
        for i in range(0, len(data), batch_size):
            chunk = data[i : i + batch_size]
            for item in chunk:
                await self.session.merge(Ticket(**item))
                total += 1
            await self.session.commit()
        return total

    async def count(self) -> int:
        result = await self.session.execute(select(func.count(Ticket.ticket_number)))
        return result.scalar_one() or 0

    async def date_range(self) -> tuple[date | None, date | None]:
        result = await self.session.execute(
            select(func.min(Ticket.issue_date), func.max(Ticket.issue_date))
        )
        row = result.one()
        return row[0], row[1]

    async def by_status(self) -> list[tuple[str, int]]:
        result = await self.session.execute(
            select(Ticket.status, func.count(Ticket.ticket_number))
            .group_by(Ticket.status)
            .order_by(func.count(Ticket.ticket_number).desc())
        )
        return [(row[0], row[1]) for row in result.all()]

    async def by_state(self) -> list[tuple[str, int]]:
        result = await self.session.execute(
            select(Ticket.state, func.count(Ticket.ticket_number))
            .group_by(Ticket.state)
            .order_by(func.count(Ticket.ticket_number).desc())
        )
        return [(row[0], row[1]) for row in result.all()]

    async def open_by_state(self) -> list[tuple[str, int]]:
        result = await self.session.execute(
            select(Ticket.state, func.count(Ticket.ticket_number))
            .where(Ticket.status == "open")
            .group_by(Ticket.state)
            .order_by(func.count(Ticket.ticket_number).desc())
        )
        return [(row[0], row[1]) for row in result.all()]

    async def get_distinct_locations(self, limit: int | None = None) -> list[str]:
        """Return distinct non-empty location strings from tickets."""
        stmt = (
            select(Ticket.location)
            .where(Ticket.location != "", Ticket.location.is_not(None))
            .distinct()
            .order_by(Ticket.location)
        )
        if limit:
            stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all() if row[0]]
