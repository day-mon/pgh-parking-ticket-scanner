"""Ticket model."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from pgh_ticket.models.base import Base
from pgh_ticket.utils import TicketView


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("idx_tickets_state_status", "state", "status"),
        Index("idx_tickets_issue_date", "issue_date"),
        Index("idx_tickets_updated_at", "updated_at"),
    )

    ticket_number: Mapped[str] = mapped_column(primary_key=True)
    vehicle_make: Mapped[str] = mapped_column(default="")
    license_plate: Mapped[str] = mapped_column(default="")
    state: Mapped[str] = mapped_column(default="")
    issue_date: Mapped[str] = mapped_column(default="")
    location: Mapped[str] = mapped_column(default="")
    violation: Mapped[str] = mapped_column(default="")
    amount_due: Mapped[str] = mapped_column(default="")
    due_date: Mapped[str] = mapped_column(default="")
    officer: Mapped[str] = mapped_column(default="")
    notes: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(default="")
    ticket_type: Mapped[str] = mapped_column(default="")
    raw_json: Mapped[str] = mapped_column(default="")
    first_seen: Mapped[str] = mapped_column(
        default=lambda: datetime.now(UTC).isoformat(),
    )
    updated_at: Mapped[str] = mapped_column(
        default=lambda: datetime.now(UTC).isoformat(),
        onupdate=lambda: datetime.now(UTC).isoformat(),
    )

    def to_ticket_view(self) -> TicketView:
        return TicketView(
            number=self.ticket_number,
            vehicle_make=self.vehicle_make,
            license_plate=self.license_plate,
            state=self.state,
            issue_date=self.issue_date,
            location=self.location,
            violation=self.violation,
            amount_due=self.amount_due,
            due_date=self.due_date,
            officer=self.officer,
            notes=self.notes,
            status=self.status,
            ticket_type=self.ticket_type,
        )
