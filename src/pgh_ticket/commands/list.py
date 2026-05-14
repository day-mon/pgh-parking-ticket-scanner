"""/list -- query tickets from the database with optional filters."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from rich.console import Console
from rich.table import Table
from sqlalchemy.ext.asyncio import AsyncSession

from pgh_ticket.commands.base import BaseCommand
from pgh_ticket.commands.common import CommonParams
from pgh_ticket.models import Ticket
from pgh_ticket.utils import TicketView

console = Console(stderr=True)


class ListCommand(BaseCommand):
    """List stored tickets with optional filters (state, status, date range)."""

    async def __call__(
        self,
        state: Annotated[
            str | None,
            Parameter(("--state",), help="filter by state code (e.g. PA)"),
        ] = None,
        status: Annotated[
            str | None,
            Parameter(("--status",), help="filter by status (e.g. Open, Paid)"),
        ] = None,
        date_from: Annotated[
            str | None,
            Parameter(("--date-from",), help="earliest issue date (YYYY-MM-DD)"),
        ] = None,
        date_to: Annotated[
            str | None,
            Parameter(("--date-to",), help="latest issue date (YYYY-MM-DD)"),
        ] = None,
        limit: Annotated[
            int,
            Parameter(("-n", "--limit"), help="max results to show"),
        ] = 50,
        *,
        session: Annotated[AsyncSession, Parameter(parse=False)] = None,  # type: ignore[assignment]
        common: CommonParams = CommonParams(),
    ) -> None:
        filters: dict[str, object] = {}
        if state:
            filters["state"] = state.upper()
        if status:
            filters["status"] = status
        if date_from:
            filters["issue_date__gte"] = date_from
        if date_to:
            filters["issue_date__lte"] = date_to

        # Build query manually since CRUDMixin.filter uses equality only
        from sqlalchemy import func, select

        stmt = select(Ticket)
        if state:
            stmt = stmt.where(Ticket.state == state.upper())
        if status:
            stmt = stmt.where(func.lower(Ticket.status) == status.lower())
        if date_from:
            stmt = stmt.where(Ticket.issue_date >= date_from)
        if date_to:
            stmt = stmt.where(Ticket.issue_date <= date_to)
        stmt = stmt.order_by(Ticket.issue_date.desc(), Ticket.ticket_number.desc())
        stmt = stmt.limit(limit)

        rows = (await session.execute(stmt)).scalars().all()

        if not rows:
            console.print("no tickets match.")
            return

        if common.verbose:
            for r in rows:
                tv = r.to_ticket_view()
                console.print(tv.verbose_str())
            console.print(f"\n[dim]{len(rows)} ticket(s)[/]")
            return

        table = Table(title=f"{len(rows)} ticket(s)")
        table.add_column("number", style="cyan", no_wrap=True)
        table.add_column("date", style="magenta")
        table.add_column("type")
        table.add_column("plate")
        table.add_column("st", justify="center")
        table.add_column("status")
        table.add_column("amount", justify="right")

        for r in rows:
            tv = r.to_ticket_view()
            table.add_row(
                tv.number,
                tv.issue_date,
                tv.ticket_type,
                tv.license_plate,
                tv.state,
                tv.status,
                tv.amount_due,
            )

        console.print(table)


list_cmd = ListCommand()
