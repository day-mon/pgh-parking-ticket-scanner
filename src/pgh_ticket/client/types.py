from __future__ import annotations

from typing import TypedDict


class SearchResult(TypedDict, total=False):
    number: str
    type: str
    plate: str
    state: str
    issue_date: str
    status: str
    amount: str
    ticket_key: str


class TicketDetail(TypedDict, total=False):
    number: str
    vehicle_make: str
    license_plate: str
    state: str
    issue_date: str
    location: str
    violation: str
    amount_due: str
    due_date: str
    officer: str
    notes: str
    status: str
    ticket_type: str
