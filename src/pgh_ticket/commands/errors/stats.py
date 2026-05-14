"""errors stats -- show error log aggregates."""

from __future__ import annotations

from typing import Annotated

from cyclopts import Parameter
from rich.console import Console
from rich.table import Table
from sqlalchemy import desc, func, select

from pgh_ticket.commands.common import CommonParams
from pgh_ticket.db import Database
from pgh_ticket.models import ErrorLog

console = Console(stderr=True, force_terminal=True)


async def stats(
    *,
    command: Annotated[
        str | None,
        Parameter(("--cmd",), help="filter by command"),
    ] = None,
    common: CommonParams = CommonParams(),
    db: Annotated[Database, Parameter(parse=False)] = None,  # type: ignore[assignment]
) -> None:
    async with db.session() as session:
        total_stmt = select(func.count()).select_from(ErrorLog)
        unresolved_stmt = select(func.count()).select_from(ErrorLog).where(ErrorLog.resolved.is_(False))
        if command:
            total_stmt = total_stmt.where(ErrorLog.command == command)
            unresolved_stmt = unresolved_stmt.where(ErrorLog.command == command)

        total = await session.scalar(total_stmt)
        unresolved = await session.scalar(unresolved_stmt)

        by_type = await session.execute(
            select(ErrorLog.error_type, func.count())
            .group_by(ErrorLog.error_type)
            .order_by(desc(func.count()))
        )
        by_cmd = await session.execute(
            select(ErrorLog.command, func.count())
            .group_by(ErrorLog.command)
            .order_by(desc(func.count()))
        )

    console.print(f"total errors: {total} | unresolved: {unresolved}")
    if command:
        console.print(f"(filtered to command: {command})")
    console.print()

    t = Table(title="by error type")
    t.add_column("type")
    t.add_column("count", justify="right")
    for typ, cnt in by_type.all():
        t.add_row(typ or "", str(cnt))
    console.print(t)

    t2 = Table(title="by command")
    t2.add_column("command")
    t2.add_column("count", justify="right")
    for cmd, cnt in by_cmd.all():
        t2.add_row(cmd or "", str(cnt))
    console.print(t2)
