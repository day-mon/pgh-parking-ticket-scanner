"""sync command -- probe for tickets issued on a specific date."""

from __future__ import annotations

import asyncio
import json
import signal
from datetime import datetime
from typing import Annotated

from cyclopts import Parameter
from cyclopts import validators as cyclopts_validators

from pgh_ticket.config import portal
from pgh_ticket.core import Database
from pgh_ticket.core.client import ClientPool, PortalClient
from pgh_ticket.core.fmt import build_simple_table, console, print_summary
from pgh_ticket.core.utils import resolve_proxy
from pgh_ticket.repos import ClusterRepo, ScanRepo, TicketRepo

from .syncer import Syncer


async def sync(
    date_str: Annotated[str, Parameter(help="target date (YYYY-MM-DD)")],
    *,
    workers: Annotated[
        int,
        Parameter(
            ("-w", "--workers"),
            help="number of concurrent requests",
            validator=cyclopts_validators.Number(gte=1),
        ),
    ] = 3,
    step: Annotated[
        int,
        Parameter(
            ("--step",),
            help="probe interval inside clusters",
            validator=cyclopts_validators.Number(gte=1),
        ),
    ] = 100,
    output: Annotated[
        str | None,
        Parameter(("-o", "--output"), help="save results to json file"),
    ] = None,
    summary: Annotated[
        bool,
        Parameter(("--summary",), help="show breakdown by state and status"),
    ] = False,
    skip_known: Annotated[
        bool,
        Parameter(("--skip-known",), help="skip numbers already in the database"),
    ] = False,
    proxy: str | None = None,
    db: Annotated[Database, Parameter(parse=False)],
) -> None:
    """Probe ticket numbers looking for a specific issue date.

    Examples:
      pgh-ticket sync 2026-05-08 -w 3 --step 200
      pgh-ticket sync 2026-05-08 -w 10 --proxy socks5://10.64.0.1:1080
    """

    target = datetime.strptime(date_str, "%Y-%m-%d").date()

    if proxy:
        console.print(f"proxy: {proxy}")
    if skip_known:
        console.print("[dim]skip-known: skipping numbers already in db[/]")
    console.print()

    known: set[str] = set()
    if skip_known:
        async with db.session() as session:
            known = await TicketRepo(session).get_all_numbers()
        console.print(f"[dim]found {len(known):,} known tickets in db[/]")

    proxy_list = resolve_proxy(proxy)
    proxy_str = proxy_list[0] if proxy_list else None
    if len(proxy_list) > 1:
        async with ClientPool(proxy_list, workers) as pool:
            syncer = Syncer(pool, db)
            found, n_errs, needs_rebuild = await syncer.run(target, workers, step, skip_known, known)
    else:
        async with PortalClient(proxy=proxy_str) as client:
            syncer = Syncer(client, db)

            loop = asyncio.get_event_loop()
            main_task: asyncio.Task | None = None

            def _on_signal() -> None:
                if main_task:
                    main_task.cancel()

            loop.add_signal_handler(signal.SIGTERM, _on_signal)
            loop.add_signal_handler(signal.SIGINT, _on_signal)

            try:
                main_task = asyncio.ensure_future(syncer.run(target, workers, step, skip_known, known))
                found, n_errs, needs_rebuild = await main_task
            except asyncio.CancelledError:
                console.print("\n[yellow]interrupted — data flushed to db on each find.[/]")
                return

    if needs_rebuild:
        console.print("[dim]rebuilding clusters from ticket data...[/]")
        async with db.session() as session:
            await ClusterRepo(session).clear()
            await ClusterRepo(session).rebuild(gap=100)

    # Record scan
    async with db.session() as session:
        await ScanRepo(session).create(
            range_start=portal.settings.lo,
            range_end=portal.settings.hi,
            until_date=date_str,
            tickets_found=len(found),
            errors=n_errs,
            duration_s=0.0,  # Will fix
        )

    console.print()

    if not found:
        console.print(f"no tickets found on {target}.")
        return

    found.sort(key=lambda t: t.issue_date)
    console.print(build_simple_table(found, date_str))

    if summary:
        print_summary(found)

    if output:
        with open(output, "w") as f:
            json.dump([t.to_dict() for t in found], f, indent=2)
        console.print(f"[dim]saved to {output}[/]")
