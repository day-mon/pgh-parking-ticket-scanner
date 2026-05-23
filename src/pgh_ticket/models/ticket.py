"""Ticket model."""

from __future__ import annotations

from datetime import date as date_type
from typing import TYPE_CHECKING

from sqlalchemy import Date, Index
from sqlalchemy.orm import Mapped, mapped_column, validates

from pgh_ticket.models.base import Base

if TYPE_CHECKING:
    from pgh_ticket.core.fmt import TicketView


def parse_date_str(s: str) -> date_type | None:
    """Parse M/D/YYYY or YYYY-MM-DD string to date."""
    from datetime import datetime

    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("idx_tickets_status_state", "status", "state"),
        Index("idx_tickets_issue_date", "issue_date"),
        Index("idx_tickets_updated_at", "updated_at"),
        Index("idx_tickets_location", "location"),
        Index("idx_tickets_violation", "violation"),
        Index("idx_tickets_officer", "officer"),
        Index("idx_tickets_license_plate", "license_plate"),
        Index("idx_tickets_ticket_key", "ticket_key"),
        # Composite date+status for year + open-status queries (dashboard)
        Index("idx_tickets_issue_date_status", "issue_date", "status"),
        # GIN trigram indexes for ILIKE/%wildcard% searches (used by dashboard)
        Index(
            "idx_tickets_plate_trgm",
            "license_plate",
            postgresql_using="gin",
            postgresql_ops={"license_plate": "gin_trgm_ops"},
        ),
        Index(
            "idx_tickets_location_trgm",
            "location",
            postgresql_using="gin",
            postgresql_ops={"location": "gin_trgm_ops"},
        ),
        Index(
            "idx_tickets_violation_trgm",
            "violation",
            postgresql_using="gin",
            postgresql_ops={"violation": "gin_trgm_ops"},
        ),
    )

    ticket_number: Mapped[str] = mapped_column(primary_key=True)
    ticket_key: Mapped[str] = mapped_column(default="")
    vehicle_make: Mapped[str] = mapped_column(default="")
    license_plate: Mapped[str] = mapped_column(default="")
    state: Mapped[str] = mapped_column(default="")
    issue_date: Mapped[date_type | None] = mapped_column(Date, default=None)
    location: Mapped[str] = mapped_column(default="")
    violation: Mapped[str] = mapped_column(default="")
    amount_due: Mapped[str] = mapped_column(default="")
    due_date: Mapped[date_type | None] = mapped_column(Date, default=None)
    officer: Mapped[str] = mapped_column(default="")
    notes: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(default="")
    ticket_type: Mapped[str] = mapped_column(default="")
    raw_json: Mapped[str] = mapped_column(default="")
    first_seen: Mapped[str] = mapped_column(default="")
    updated_at: Mapped[str] = mapped_column(default="")

    @validates("issue_date", "due_date")
    def _validate_date(self, _key: str, value: object) -> date_type | None:
        if isinstance(value, str) and value:
            return parse_date_str(value)
        if isinstance(value, date_type) or value is None:
            return value
        return None

    @validates("status")
    def _validate_status(self, _key: str, value: object) -> str:
        if isinstance(value, str):
            return value.lower()
        return ""

    def to_view(self) -> TicketView:
        from pgh_ticket.core.fmt import TicketView

        return TicketView(
            number=self.ticket_number,
            vehicle_make=self.vehicle_make,
            license_plate=self.license_plate,
            state=self.state,
            issue_date=self.issue_date.strftime("%m/%d/%Y") if self.issue_date else "",
            location=self.location,
            violation=self.violation,
            amount_due=self.amount_due,
            due_date=self.due_date.strftime("%m/%d/%Y") if self.due_date else "",
            officer=self.officer,
            notes=self.notes,
            status=self.status,
            ticket_type=self.ticket_type,
            ticket_key=self.ticket_key,
        )

    def to_model_dict(self) -> dict[str, object]:
        return {
            "ticket_number": self.ticket_number,
            "ticket_key": self.ticket_key,
            "vehicle_make": self.vehicle_make,
            "license_plate": self.license_plate,
            "state": self.state,
            "issue_date": self.issue_date,
            "location": self.location,
            "violation": self.violation,
            "amount_due": self.amount_due,
            "due_date": self.due_date,
            "officer": self.officer,
            "notes": self.notes,
            "status": self.status,
            "ticket_type": self.ticket_type,
        }
