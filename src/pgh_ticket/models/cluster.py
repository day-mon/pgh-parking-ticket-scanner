"""Cluster model."""

from __future__ import annotations

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from pgh_ticket.models.base import Base


class Cluster(Base):
    __tablename__ = "clusters"
    __table_args__ = (
        Index("idx_cluster_range_start", "range_start"),
        Index("idx_cluster_range_end", "range_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    range_start: Mapped[int] = mapped_column()
    range_end: Mapped[int] = mapped_column()
    last_scanned: Mapped[str] = mapped_column(default="")
    ticket_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(default="")
