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
    help_epilogue="Data stored in ~/.local/share/pgh-ticket/tickets.db",
    group_arguments=None,
)
app.meta.group_parameters = Group("Session Parameters", sort_key=0)


@app.meta.default
async def main(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    db_path: Annotated[
        str | None,
        Parameter(("--db",), help="path to sqlite database"),
    ] = None,
) -> None:
    """Meta-app launcher: creates Database once, injects it into commands."""
    db = create_database(db_path)
    await db.init()

    command, bound, ignored = app.parse_args(tokens)

    extra: dict[str, object] = {}
    if "db" in ignored:
        extra["db"] = db
    if "session" in ignored:
        async with db.session() as session:
            extra["session"] = session
            return await command(*bound.args, **bound.kwargs, **extra)

    return await command(*bound.args, **bound.kwargs, **extra)


# Import and register commands

app.command(lookup, name="lookup")
app.command(scan, name="scan")
app.command(sync, name="sync")
app.command(list_cmd, name="list")
app.command(stats, name="stats")

# Sub-apps

app.command(backfill_app, name="backfill")
app.command(errors_app, name="errors")


def main() -> None:
    asyncio.run(app.meta())


if __name__ == "__main__":
    main()

main_entry = main
