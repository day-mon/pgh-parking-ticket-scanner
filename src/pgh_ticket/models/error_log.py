"""ErrorLog model."""

from __future__ import annotations

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from pgh_ticket.models.base import Base


class ErrorLog(Base):
    __tablename__ = "error_logs"
    __table_args__ = (
        Index("idx_errors_resolved", "resolved"),
        Index("idx_errors_command", "command"),
        Index("idx_errors_number", "number"),
        Index("idx_errors_type", "error_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column()
    command: Mapped[str] = mapped_column(default="")
    error_type: Mapped[str] = mapped_column(default="")
    message: Mapped[str] = mapped_column(default="")
    retries: Mapped[int] = mapped_column(default=0)
    resolved: Mapped[bool] = mapped_column(default=False)
    first_seen: Mapped[str] = mapped_column(default="")
    last_seen: Mapped[str] = mapped_column(default="")
