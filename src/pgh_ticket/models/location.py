"""Location model."""

from __future__ import annotations

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from pgh_ticket.models.base import Base


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        Index("idx_locations_lat_lon", "latitude", "longitude"),
    )

    raw_location: Mapped[str] = mapped_column(primary_key=True)
    address: Mapped[str] = mapped_column(default="")
    latitude: Mapped[float | None] = mapped_column(default=None)
    longitude: Mapped[float | None] = mapped_column(default=None)
    geocoded_at: Mapped[str] = mapped_column(default="")
    ticket_count: Mapped[int] = mapped_column(default=0)
