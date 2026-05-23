"""errors clear -- delete all error logs."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from sqlalchemy.ext.asyncio import AsyncSession

from pgh_ticket.core.fmt import console
from pgh_ticket.repos import ErrorLogRepo


async def clear(
    *,
    session: Annotated[AsyncSession, Parameter(parse=False)],
) -> None:
    """Clear all error logs."""

    repo = ErrorLogRepo(session)
    count = await repo.clear()
    console.print(f"[green]cleared {count} error logs.[/]")
