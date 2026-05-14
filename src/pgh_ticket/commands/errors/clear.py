"""errors clear -- delete error log entries."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from rich.console import Console
from sqlalchemy import delete

from pgh_ticket.commands.common import CommonParams
from pgh_ticket.db import Database
from pgh_ticket.models import ErrorLog

console = Console(stderr=True, force_terminal=True)


async def clear(
    *,
    command: Annotated[
        str | None,
        Parameter(("--cmd",), help="filter by command"),
    ] = None,
    unresolved_only: Annotated[
        bool,
        Parameter(("--unresolved", "-u"), help="only clear unresolved"),
    ] = False,
    common: CommonParams = CommonParams(),
    db: Annotated[Database, Parameter(parse=False)] = None,  # type: ignore[assignment]
) -> None:
    async with db.session() as session:
        stmt = delete(ErrorLog)
        if unresolved_only:
            stmt = stmt.where(ErrorLog.resolved.is_(False))
        if command:
            stmt = stmt.where(ErrorLog.command == command)
        await session.execute(stmt)
        await session.commit()
    console.print("deleted error log entries.")
