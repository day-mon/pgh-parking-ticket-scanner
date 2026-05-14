"""errors list -- show error log entries."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from rich.console import Console
from sqlalchemy import desc, select

from pgh_ticket.commands.common import CommonParams
from pgh_ticket.db import Database
from pgh_ticket.models import ErrorLog
from pgh_ticket.commands.errors._table import build_table

console = Console(stderr=True, force_terminal=True)


async def list_(
    *,
    limit: Annotated[
        int,
        Parameter(("-n", "--limit"), help="max rows to show"),
    ] = 50,
    command: Annotated[
        str | None,
        Parameter(("--cmd",), help="filter by command (scan, sync, lookup)"),
    ] = None,
    unresolved_only: Annotated[
        bool,
        Parameter(("--unresolved", "-u"), help="only show unresolved"),
    ] = False,
    common: CommonParams = CommonParams(),
    db: Annotated[Database, Parameter(parse=False)] = None,  # type: ignore[assignment]
) -> None:
    async with db.session() as session:
        stmt = select(ErrorLog).order_by(desc(ErrorLog.last_seen))
        if unresolved_only:
            stmt = stmt.where(ErrorLog.resolved.is_(False))
        if command:
            stmt = stmt.where(ErrorLog.command == command)
        rows = list((await session.execute(stmt.limit(limit))).scalars().all())
    if not rows:
        console.print("no error logs found.")
        return
    console.print(build_table(rows, limit))
