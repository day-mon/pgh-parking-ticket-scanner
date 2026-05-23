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
    help_prologue="An async scanner for the Pittsburgh Parking Authority portal.\n\nExamples:\n  pgh-ticket lookup 9244895\n  pgh-ticket lookup 8950000-8950005\n  pgh-ticket scan 8950000-9245300 --until 2026-05-13 -w 20 --step 100\n  pgh-ticket sync 2026-05-08 -w 3 --step 200\n  pgh-ticket list --state PA --status Open -n 20\n  pgh-ticket stats",
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
    if command is None:
        return  # --version (no further action)
    if "db" in ignored:
        extra["db"] = db

    def _run() -> object:
        return command(*bound.args, **bound.kwargs, **extra)

    if "session" in ignored:
        async with db.session() as session:
            extra["session"] = session
            result = _run()
            if asyncio.iscoroutine(result):
                await result
    else:
        result = _run()
        if asyncio.iscoroutine(result):
            await result


def main_entry() -> None:
    """Synchronous entry point for console_scripts."""
    asyncio.run(_dispatch())


if __name__ == "__main__":
    asyncio.run(_dispatch())
