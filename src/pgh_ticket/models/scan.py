"""Scan history model."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from pgh_ticket.models.base import Base
from pgh_ticket.models.mixins import PKMixin


class Scan(Base, PKMixin):
    __tablename__ = "scans"
    __table_args__ = (
        Index("idx_scans_scanned_at", "scanned_at"),
        Index("idx_scans_range_start", "range_start"),
    )

    range_start: Mapped[int] = mapped_column()
    range_end: Mapped[int] = mapped_column()
    until_date: Mapped[str] = mapped_column()
    tickets_found: Mapped[int] = mapped_column()
    errors: Mapped[int] = mapped_column(default=0)
    duration_s: Mapped[float] = mapped_column(default=0.0)
    scanned_at: Mapped[str] = mapped_column(
        default=lambda: datetime.now(UTC).isoformat(),
    )
