"""Display formatting and CLI helpers."""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

console = Console(
    stderr=True,
    force_terminal=True,
    no_color=os.environ.get("NO_COLOR", "") != "",
)


@dataclass
class TicketView:
    """Pure display formatting for a parking ticket."""

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
    ticket_key: str = ""

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

    def to_dict(self) -> dict[str, object]:
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
            "ticket_key": self.ticket_key,
        }

    def to_model_dict(self) -> dict[str, object]:
        """Return a dict keyed for the Ticket model."""
        return {
            "ticket_number": self.number,
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


def parse_range(number_range: str) -> tuple[int, int]:
    lo, hi = (int(x) for x in number_range.split("-"))
    return lo, hi


def fmt_status(
    label: str,
    count: int,
    stored: int = 0,
    errs: int = 0,
    in_flight: int = 0,
    skipped: int = 0,
) -> str:
    parts = [f"[green]{count}[/] {label}", f"[dim]{stored}[/] stored"]
    if in_flight:
        parts.append(f"[yellow]{in_flight}[/] in flight")
    if errs:
        parts.append(f"[red]{errs}[/] errs")
    if skipped:
        parts.append(f"[dim]⏭ {skipped}[/] no key")
    return " • ".join(parts)


def make_progress(*, transient: bool = True) -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        TextColumn("•"),
        TextColumn("{task.fields[status]}"),
        console=console,
        transient=transient,
    )


def build_ticket_table(found: list[TicketView], title: str | None = None) -> Table:
    if title is None:
        dates = {d for t in found if (d := parse_date(t.issue_date)) is not None}
        if dates:
            title = f"{len(found)} tickets from {min(dates)} to {max(dates)}"
        else:
            title = f"{len(found)} tickets"

    table = Table(title=title)
    table.add_column("number", style="cyan", no_wrap=True)
    table.add_column("date", style="magenta")
    table.add_column("type")
    table.add_column("plate")
    table.add_column("st", justify="center")
    table.add_column("status")
    table.add_column("amount", justify="right")
    for t in found:
        table.add_row(
            t.number,
            t.issue_date,
            t.ticket_type,
            t.license_plate,
            t.state,
            t.status,
            t.amount_due,
        )
    return table


def build_simple_table(found: list[TicketView], target: str) -> Table:
    table = Table(title=f"{len(found)} tickets on {target}")
    table.add_column("number", style="cyan", no_wrap=True)
    table.add_column("type")
    table.add_column("plate")
    table.add_column("st", justify="center")
    table.add_column("status")
    table.add_column("amount", justify="right")
    for t in found:
        table.add_row(
            t.number,
            t.ticket_type,
            t.license_plate,
            t.state,
            t.status,
            t.amount_due,
        )
    return table


def print_summary(tickets: list[TicketView]) -> None:
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
        print(f"    {label:<25s}  {n:>5d}  ({100 * n / total:5.1f}%)")

    print()
    print("  by state:")
    for label, n in state_cnt.most_common():
        print(f"    {label:<4s}  {n:>5d}  ({100 * n / total:5.1f}%)")

    if open_state:
        open_total = sum(open_state.values())
        print()
        print(f"  open by state ({open_total}):")
        for label, n in open_state.most_common():
            print(f"    {label:<4s}  {n:>5d}  ({100 * n / open_total:5.1f}%)")
