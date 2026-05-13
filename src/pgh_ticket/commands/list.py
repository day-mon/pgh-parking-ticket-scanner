from __future__ import annotations

import sys
from typing import Annotated

from cyclopts import Parameter

from pgh_ticket.db import Database
from pgh_ticket.utils import TicketData


async def run(
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
    verbose: Annotated[
        bool,
        Parameter(("-v", "--verbose"), help="show full ticket details"),
    ] = False,
    db_path: Annotated[
        str | None,
        Parameter(("--db",), help="path to sqlite database", show=False),
    ] = None,
) -> None:
    db = Database(db_path)
    db.init()
    results = db.search_tickets(
        state=state,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )

    if not results:
        print("no tickets match.", file=sys.stderr)
        return

    for r in results:
        td = TicketData.from_db(r)
        print(td.verbose_str() if verbose else str(td))

    print(f"\n{len(results)} ticket(s)", file=sys.stderr)
