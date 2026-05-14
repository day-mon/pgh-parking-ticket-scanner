"""lookup -- one-off ticket lookups by number (or range)."""

from __future__ import annotations

import asyncio
import sys
from typing import Annotated

from cyclopts import Parameter
from cyclopts import validators as cyclopts_validators
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)

from pgh_ticket.client import Client
from pgh_ticket.commands.base import BaseCommand
from pgh_ticket.commands.common import CommonParams
from pgh_ticket.db import Database
from pgh_ticket.models import ErrorLog, Ticket
from pgh_ticket.utils import TicketView, expand_range

console = Console(stderr=True, force_terminal=True)


def _require_at_least_one(value, _):
    if not value:
        raise ValueError("at least one ticket number required")


class LookupCommand(BaseCommand):
    """Look up tickets by number (or range) and store in the database."""

    async def __call__(
        self,
        *tickets: Annotated[
            str,
            Parameter(validator=_require_at_least_one),
        ],
        workers: Annotated[
            int,
            Parameter(
                ("-j", "--workers"),
                help="number of concurrent requests",
                validator=cyclopts_validators.Number(gte=1),
            ),
        ] = 10,
        common: CommonParams = CommonParams(),
        db: Annotated[Database, Parameter(parse=False)] = None,  # type: ignore[assignment]
    ) -> None:

        expanded: list[str] = []
        for t in tickets:
            expanded.extend(expand_range(t))

        sem = asyncio.Semaphore(workers)
        lock = asyncio.Lock()
        found: list[TicketView] = []
        seen: set[str] = set()
        errs = [0]

        async def fetch_one(n: str) -> list[TicketView]:
            async with sem:
                try:
                    results = await cl.search(n)
                except Exception as exc:
                    async with lock:
                        errs[0] += 1
                    async with db.session() as session:
                        await ErrorLog.log(session, number=n, command="lookup", exc=exc)
                    return []

            views: list[TicketView] = []
            async with lock:
                for r in results:
                    tv = r.to_ticket_view()
                    if tv.number not in seen:
                        seen.add(tv.number)
                        views.append(tv)
            return views

        async with Client(proxy=common.proxy) as cl:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TaskProgressColumn(),
                TextColumn("•"),
                TextColumn("{task.fields[status]}"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task(
                    "looking up", total=len(expanded), status="starting..."
                )

                async def work(n: str) -> None:
                    views = await fetch_one(n)
                    async with lock:
                        found.extend(views)
                        progress.update(
                            task,
                            advance=1,
                            status=f"[green]{len(found)}[/] found • [red]{errs[0]}[/] errs",
                        )

                await asyncio.gather(*[work(n) for n in expanded], return_exceptions=True)

        if found:
            async with db.session() as session:
                for tv in found:
                    await session.merge(Ticket(**tv.to_model_dict()))
                await session.commit()

            for tv in found:
                print(tv.verbose_str() if common.verbose else str(tv))
        else:
            console.print("no tickets found.")


lookup_cmd = LookupCommand()
