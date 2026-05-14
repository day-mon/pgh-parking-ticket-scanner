"""/backfill -- enrich tickets missing detail fields (officer, location, etc.)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated

from cyclopts import Parameter
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from sqlalchemy import select

from pgh_ticket.client import Client
from pgh_ticket.commands.base import BaseCommand
from pgh_ticket.commands.common import CommonParams
from cyclopts import validators as cyclopts_validators

from pgh_ticket.db import Database
from pgh_ticket.models import Ticket
from pgh_ticket.utils import TicketView
from pgh_ticket import validators as pgh_validators

console = Console(stderr=True, force_terminal=True)


class BackfillCommand(BaseCommand):
    """Re-query the portal for tickets missing detail fields (officer, location, etc.)."""

    async def __call__(
        self,
        workers: Annotated[
            int,
            Parameter(
                ("-j", "--workers"),
                help="number of concurrent requests",
                validator=cyclopts_validators.Number(gte=1),
            ),
        ] = 5,
        limit: Annotated[
            int | None,
            Parameter(
                ("-n", "--limit"),
                help="max tickets to backfill (default: all)",
                validator=cyclopts_validators.Number(gte=1),
            ),
        ] = None,
        *,
        common: CommonParams = CommonParams(),
        db: Annotated[Database, Parameter(parse=False)] = None,  # type: ignore[assignment]
    ) -> None:
        async with db.session() as session:
            stmt = select(Ticket).where(Ticket.officer == "")
            if limit:
                stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            unfilled = result.scalars().all()

        if not unfilled:
            console.print("[green]all tickets are already filled.[/]")
            return

        total = len(unfilled)
        console.print(f"backfilling [bold]{total}[/] tickets...")

        lock = asyncio.Lock()
        sem = asyncio.Semaphore(workers)
        done = 0

        async with Client(proxy=common.proxy) as cl:

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("•"),
                TextColumn("{task.completed}/{task.total}"),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("backfilling", total=total)

                async def fill(row: Ticket) -> None:
                    nonlocal done

                    tv = row.to_ticket_view()
                    if not tv.number:
                        async with lock:
                            done += 1
                            progress.update(task, advance=1)
                        return

                    async with sem:
                        try:
                            results = await cl.search(tv.number)
                        except Exception:
                            async with lock:
                                done += 1
                                progress.update(task, advance=1)
                            return

                    for r in results:
                        if not r.ticket_key:
                            continue
                        try:
                            details = await cl.details(r.ticket_key)
                        except Exception:
                            continue
                        if details:
                            r = r.merge(details)
                            async with db.session() as session:
                                await session.merge(Ticket(**r.to_ticket_view().to_model_dict()))
                                await session.commit()

                    async with lock:
                        done += 1
                        progress.update(task, advance=1)

                await asyncio.gather(*[fill(r) for r in unfilled], return_exceptions=True)

        console.print(f"\n[bold]backfilled {done}/{total} tickets[/]")


backfill_cmd = BackfillCommand()
