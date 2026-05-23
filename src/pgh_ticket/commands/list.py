"""list -- query tickets from the database with optional filters."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from sqlalchemy.ext.asyncio import AsyncSession

from pgh_ticket.core.fmt import build_ticket_table, console
from pgh_ticket.repos import TicketRepo


async def list_(
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
    sort: Annotated[
        str,
        Parameter(("--sort",), help="sort by: date, updated, number"),
    ] = "date",
    *,
    verbose: bool = False,
    session: Annotated[AsyncSession, Parameter(parse=False)],
) -> None:
    """List stored tickets with optional filters."""

    repo = TicketRepo(session)
    rows = await repo.list_tickets(
        state=state,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        sort=sort,
    )

    if not rows:
        console.print("no tickets match.")
        return

    if verbose:
        for r in rows:
            console.print(r.to_view().verbose_str())
        console.print(f"\n[dim]{len(rows)} ticket(s)[/]")
        return

    views = [r.to_view() for r in rows]
    console.print(build_ticket_table(views, title=f"{len(rows)} ticket(s)"))
