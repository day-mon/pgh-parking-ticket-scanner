"""errors retry -- mark unresolved errors for retry."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from rich.console import Console
from sqlalchemy import select

from pgh_ticket.commands.common import CommonParams
from pgh_ticket.db import Database
from pgh_ticket.models import ErrorLog

console = Console(stderr=True, force_terminal=True)


async def retry(
    *,
    command: Annotated[
        str | None,
        Parameter(("--cmd",), help="filter by command"),
    ] = None,
    common: CommonParams = CommonParams(),
    db: Annotated[Database, Parameter(parse=False)] = None,  # type: ignore[assignment]
) -> None:
    async with db.session() as session:
        stmt = select(ErrorLog).where(ErrorLog.resolved.is_(False))
        if command:
            stmt = stmt.where(ErrorLog.command == command)
        rows = list((await session.execute(stmt)).scalars().all())
        if not rows:
            console.print("no unresolved errors to retry.")
            return
        for r in rows:
            r.retries += 1
        await session.commit()
    console.print(f"marked {len(rows)} errors for retry. run the original command again.")
