"""pgh-ticket — Pittsburgh parking ticket scanner."""

from __future__ import annotations

import asyncio
from typing import Annotated

from cyclopts import App, Group, Parameter

from pgh_ticket.commands.backfill import backfill_app
from pgh_ticket.commands.errors import errors_app
from pgh_ticket.commands.list import list_ as list_cmd
from pgh_ticket.commands.lookup import lookup
from pgh_ticket.commands.scan.command import scan
from pgh_ticket.commands.stats import stats
from pgh_ticket.commands.sync.command import sync
from pgh_ticket.core import create_database

app = App(
    help="Pittsburgh parking ticket scanner",
    help_prologue="An async scanner for the Pittsburgh Parking Authority portal.",
    help_epilogue="Data stored in PostgreSQL.",
    group_arguments=None,
)
app.meta.group_parameters = Group("Session Parameters", sort_key=0)


# Import and register commands

app.command(lookup, name="lookup")
app.command(list_cmd, name="list")
app.command(stats, name="stats")
app.command(scan, name="scan")
app.command(sync, name="sync")
app.command(errors_app, name="errors")
app.command(backfill_app, name="backfill")


async def _dispatch() -> None:
    """Parse args, create DB, inject session, call command."""
    db = create_database()
    await db.init()
    command, bound, ignored = app.parse_args()
    extra: dict[str, object] = {}
    if "db" in ignored:
        extra["db"] = db
    if "session" in ignored:
        async with db.session() as session:
            extra["session"] = session
            return await command(*bound.args, **bound.kwargs, **extra)
    return await command(*bound.args, **bound.kwargs, **extra)


def main_entry() -> None:
    """Synchronous entry point for console_scripts."""
    asyncio.run(_dispatch())


if __name__ == "__main__":
    asyncio.run(_dispatch())
