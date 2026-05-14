"""pgh-ticket — Pittsburgh parking ticket scanner."""

import asyncio
from typing import Annotated

from cyclopts import App, Group, Parameter
from sqlalchemy.ext.asyncio import AsyncSession

from pgh_ticket.commands.backfill import backfill_cmd
from pgh_ticket.commands.errors import errors_app
from pgh_ticket.commands.list import list_cmd
from pgh_ticket.commands.lookup import lookup_cmd
from pgh_ticket.commands.scan import scan_cmd
from pgh_ticket.commands.stats import stats_cmd
from pgh_ticket.commands.sync import sync_cmd
from pgh_ticket.db import create_database, Database

app = App(
    help="Pittsburgh parking ticket scanner",
    help_prologue="An async scanner for the Pittsburgh Parking Authority portal.",
    help_epilogue="Data stored in ~/.local/share/pgh-ticket/tickets.db",
    group_arguments=None,
)
app.meta.group_parameters = Group("Session Parameters", sort_key=0)


@app.meta.default
async def launcher(
    *tokens: Annotated[str, Parameter(show=False, allow_leading_hyphen=True)],
    db_path: Annotated[
        str | None,
        Parameter(("--db",), help="path to sqlite database"),
    ] = None,
):
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
            result = command(*bound.args, **bound.kwargs, **extra)
            if asyncio.iscoroutine(result):
                result = await result
            return result

    result = command(*bound.args, **bound.kwargs, **extra)
    if asyncio.iscoroutine(result):
        result = await result
    return result


# Bind __call__ as a method on each instance so cyclopts can inspect the signature.
app.command(lookup_cmd.__call__, name="lookup")  # type: ignore[arg-type]
app.command(scan_cmd.__call__, name="scan")  # type: ignore[arg-type]
app.command(sync_cmd.__call__, name="sync")  # type: ignore[arg-type]
app.command(list_cmd.__call__, name="list")  # type: ignore[arg-type]
app.command(stats_cmd.__call__, name="stats")  # type: ignore[arg-type]
app.command(backfill_cmd.__call__, name="backfill")  # type: ignore[arg-type]
app.command(errors_app, name="errors")  # type: ignore[arg-type]

if __name__ == "__main__":
    app.meta()


# Entry point: cyclopts entry_points can't do app.meta, so expose a callable.
main = app.meta
