"""Cluster repository."""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pgh_ticket.models import Cluster, Ticket


class ClusterRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session: AsyncSession = session

    async def all(self) -> Sequence[Cluster]:
        result = await self.session.execute(select(Cluster).order_by(Cluster.range_start))
        return result.scalars().all()

    async def clear(self) -> None:
        await self.session.execute(delete(Cluster))
        await self.session.commit()

    async def rebuild(self, gap: int = 100) -> list[Cluster]:
        """Rebuild clusters from all tickets."""
        result = await self.session.execute(
            select(Ticket.ticket_number).order_by(Ticket.ticket_number)
        )
        nums = [int(row[0]) for row in result.all()]

        if not nums:
            return []

        built: list[tuple[int, int]] = []
        start = end = nums[0]
        for n in nums[1:]:
            if n - end <= gap:
                end = n
            else:
                built.append((start, end))
                start = end = n
        built.append((start, end))

        created: list[Cluster] = []
        for s, e in built:
            count_result = await self.session.execute(
                select(func.count(Ticket.ticket_number)).where(
                    Ticket.ticket_number >= str(s),
                    Ticket.ticket_number <= str(e),
                )
            )
            count = count_result.scalar_one() or 0
            cluster = Cluster(
                range_start=s,
                range_end=e,
                ticket_count=count,
                created_at=datetime.datetime.now(datetime.UTC).isoformat(),
            )
            self.session.add(cluster)
            created.append(cluster)

        await self.session.commit()
        return created

    @staticmethod
    def build_probe_ranges(
        clusters: Sequence[Cluster],
        step: int,
        lo: int,
        hi: int,
        frontier_step: int = 500,
    ) -> list[tuple[int, int, int]]:
        ranges: list[tuple[int, int, int]] = []
        max_end = lo
        for c in clusters:
            ranges.append((c.range_start, c.range_end, step))
            max_end = max(max_end, c.range_end)
        if max_end < hi:
            ranges.append((max_end + 1, hi, frontier_step))
        return ranges
