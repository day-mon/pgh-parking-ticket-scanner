from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from itertools import chain
from typing import Any


def expand_range(arg: str) -> list[str]:
    parts = arg.split("-")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        lo, hi = int(parts[0]), int(parts[1])
        return [str(i) for i in range(lo, hi + 1)]
    return [arg]


def parse_date(s: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


@dataclass
class TicketData:
    number: str = ""
    vehicle_make: str = ""
    license_plate: str = ""
    state: str = ""
    issue_date: str = ""
    location: str = ""
    violation: str = ""
    amount_due: str = ""
    due_date: str = ""
    officer: str = ""
    notes: str = ""
    status: str = ""
    ticket_type: str = ""

    @classmethod
    def from_api(cls, data: dict) -> TicketData:
        return cls(
            number=data.get("number", ""),
            vehicle_make=data.get("vehicle_make", ""),
            license_plate=data.get("license_plate", data.get("plate", "")),
            state=data.get("state", ""),
            issue_date=data.get("issue_date", ""),
            location=data.get("location", ""),
            violation=data.get("violation", ""),
            amount_due=data.get("amount_due", data.get("amount", "")),
            due_date=data.get("due_date", ""),
            officer=data.get("officer", ""),
            notes=data.get("notes", ""),
            status=data.get("status", ""),
            ticket_type=data.get("ticket_type", data.get("type", "")),
        )

    @classmethod
    def from_db(cls, data: dict) -> TicketData:
        return cls(
            number=data.get("ticket_number", data.get("number", "")),
            vehicle_make=data.get("vehicle_make", ""),
            license_plate=data.get("license_plate", ""),
            state=data.get("state", ""),
            issue_date=data.get("issue_date", ""),
            location=data.get("location", ""),
            violation=data.get("violation", ""),
            amount_due=data.get("amount_due", ""),
            due_date=data.get("due_date", ""),
            officer=data.get("officer", ""),
            notes=data.get("notes", ""),
            status=data.get("status", ""),
            ticket_type=data.get("ticket_type", ""),
        )

    def __str__(self) -> str:
        return (
            f"[{self.number:<12s}] {self.issue_date:<12s}  "
            f"{self.ticket_type:<12s}  {self.license_plate:<12s}  "
            f"{self.state:<4s}  {self.status:<25s}  {self.amount_due:<8s}"
        )

    def verbose_str(self) -> str:
        extra = []
        for k in ("vehicle_make", "location", "violation", "due_date", "officer", "notes"):
            if v := getattr(self, k, ""):
                extra.append(f"    {k}: {v}")
        return f"{self}\n" + "\n".join(extra) if extra else str(self)

    def to_dict(self) -> dict:
        return {
            "number": self.number,
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


def print_summary(tickets: list[TicketData]) -> None:
    status_cnt: Counter[str] = Counter()
    state_cnt: Counter[str] = Counter()
    open_state: Counter[str] = Counter()

    for t in tickets:
        status_cnt[t.status.strip()] += 1
        if t.state:
            state_cnt[t.state] += 1
        if t.status.lower() == "open":
            open_state[t.state] += 1

    total = len(tickets)
    print()
    print("  by status:")
    for label, n in status_cnt.most_common():
        print(f"    {label:<25s}  {n:>5d}  ({100*n/total:5.1f}%)")

    print()
    print("  by state:")
    for label, n in state_cnt.most_common():
        print(f"    {label:<4s}  {n:>5d}  ({100*n/total:5.1f}%)")

    if open_state:
        open_total = sum(open_state.values())
        print()
        print(f"  open by state ({open_total}):")
        for label, n in open_state.most_common():
            print(f"    {label:<4s}  {n:>5d}  ({100*n/open_total:5.1f}%)")
