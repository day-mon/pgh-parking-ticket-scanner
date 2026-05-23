"""Scan model."""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from pgh_ticket.models.base import Base


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(primary_key=True)
    range_start: Mapped[int] = mapped_column()
    range_end: Mapped[int] = mapped_column()
    until_date: Mapped[str] = mapped_column()
    tickets_found: Mapped[int] = mapped_column(default=0)
    errors: Mapped[int] = mapped_column(default=0)
    duration_s: Mapped[float] = mapped_column(default=0.0)
    scanned_at: Mapped[str] = mapped_column(default="")
