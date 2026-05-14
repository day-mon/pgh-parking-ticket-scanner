"""Cluster model — tracks contiguous ranges where tickets have been found."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Sequence

from sqlalchemy import Index, select
from sqlalchemy.orm import Mapped, mapped_column

from pgh_ticket.models.base import Base
from pgh_ticket.models.mixins import PKMixin


class Cluster(Base, PKMixin):
    __tablename__ = "clusters"
    __table_args__ = (
        Index("idx_cluster_range_start", "range_start"),
        Index("idx_cluster_range_end", "range_end"),
    )

    range_start: Mapped[int] = mapped_column()
    range_end: Mapped[int] = mapped_column()
    last_scanned: Mapped[str] = mapped_column(default="")
    ticket_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(
        default=lambda: datetime.now(UTC).isoformat(),
    )

    @classmethod
    async def rebuild_from_tickets(cls, session, gap: int = 100) -> list["Cluster"]:
        """Rebuild clusters from all tickets in the database.

        Contiguous numbers within ``gap`` of each other are merged into a single cluster.
        Returns the newly created cluster objects.
        """
        from pgh_ticket.models import Ticket

        nums_result = await session.execute(
            select(Ticket.ticket_number).order_by(Ticket.ticket_number)
        )
        nums = [int(row[0]) for row in nums_result.all()]

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
            count_result = await session.execute(
                select(Ticket).where(
                    Ticket.ticket_number >= str(s),
                    Ticket.ticket_number <= str(e),
                )
            )
            count = len(count_result.scalars().all())
            cluster = cls(range_start=s, range_end=e, ticket_count=count)
            session.add(cluster)
            created.append(cluster)

        await session.commit()
        return created

    @staticmethod
    def build_probe_ranges(
        clusters: Sequence[Cluster],
        step: int,
        lo: int,
        hi: int,
        frontier_step: int = 500,
    ) -> list[tuple[int, int, int]]:
        """Build (start, end, step) probe ranges from known clusters + frontier.

        Each cluster is probed at ``step`` intervals. Everything beyond the last
        cluster is probed at ``frontier_step`` until ``hi``.
        """
        ranges: list[tuple[int, int, int]] = []
        max_end = lo
        for c in clusters:
            ranges.append((c.range_start, c.range_end, step))
            max_end = max(max_end, c.range_end)
        if max_end < hi:
            ranges.append((max_end + 1, hi, frontier_step))
        return ranges
