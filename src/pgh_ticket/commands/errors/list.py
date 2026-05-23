"""errors list -- show unresolved error logs."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from rich.table import Table
from sqlalchemy.ext.asyncio import AsyncSession

from pgh_ticket.core.fmt import console
from pgh_ticket.repos import ErrorLogRepo


async def list_(
    limit: Annotated[
        int,
        Parameter(("-n", "--limit"), help="max rows to show"),
    ] = 50,
    *,
    session: Annotated[AsyncSession, Parameter(parse=False)],
) -> None:
    """List unresolved error logs."""

    repo = ErrorLogRepo(session)
    rows = await repo.list_unresolved()

    if not rows:
        console.print("[green]no unresolved errors.[/]")
        return

    table = Table(title=f"unresolved errors ({len(rows)} total)")
    table.add_column("number", style="cyan")
    table.add_column("command")
    table.add_column("type", style="red")
    table.add_column("retries", justify="right")
    table.add_column("last seen", style="dim")
    table.add_column("message", style="dim")

    for row in rows[:limit]:
        table.add_row(
            row.number,
            row.command,
            row.error_type,
            str(row.retries),
            row.last_seen[:19],
            row.message[:60],
        )

    console.print(table)
