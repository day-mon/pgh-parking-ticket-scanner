"""scan command -- two-phase ticket collection over a number range."""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Annotated

from cyclopts import Parameter
from cyclopts import validators as cyclopts_validators

from pgh_ticket.core import Database, TicketView, parse_range
from pgh_ticket.core.fmt import console, build_ticket_table, print_summary
from pgh_ticket.core.utils import resolve_proxy
from pgh_ticket.core.client import ClientPool, PortalClient
from pgh_ticket.repos import ScanRepo

from .scanner import Scanner


async def scan(
    number_range: Annotated[
        str,
        Parameter(help="ticket number range (e.g. 8950000-9245300)"),
    ],
    *,
    until: Annotated[
        str,
        Parameter(("-u", "--until"), help="upper date bound (YYYY-MM-DD)"),
    ],
    workers: Annotated[
        int,
        Parameter(
            ("-j", "--workers"),
            help="number of concurrent requests",
            validator=cyclopts_validators.Number(gte=1),
        ),
    ] = 20,
    step: Annotated[
        int,
        Parameter(
            ("--step",),
            help="probe interval between numbers",
            validator=cyclopts_validators.Number(gte=1),
        ),
    ] = 50,
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
    proxy: list[str] | None = None,
    db: Annotated[Database, Parameter(parse=False)],
) -> None:
    """Two-phase scan: probe for clusters, then deep-scan windows."""

    target = datetime.strptime(until, "%Y-%m-%d").date()
    lo, hi = parse_range(number_range)

    console.print(f"range: {lo:,} to {hi:,} ({(hi - lo + 1):,} numbers)")
    console.print(f"until: {target} | step: {step} | workers: {workers}")
    if proxy:
        console.print(f"proxy: {proxy}")
    if skip_known:
        console.print("[dim]skip-known: skipping numbers already in db[/]")
    console.print()

    t0 = time.monotonic()

    proxies = resolve_proxy(proxy)
    proxy_list: list[str] = []
    if isinstance(proxies, list):
        proxy_list = proxies
    elif isinstance(proxies, str):
        proxy_list = [proxies]

    if len(proxy_list) > 1:
        console.print(f"using [yellow]{len(proxy_list)}[/] proxies with [yellow]{workers}[/] workers")
        async with ClientPool(proxy_list, workers) as pool:
            scanner = Scanner(pool, db)
            found, n_errs = await scanner.run(lo, hi, target, step, workers, skip_known)
    else:
        async with PortalClient(proxy=proxies) as client:
            scanner = Scanner(client, db)
            found, n_errs = await scanner.run(lo, hi, target, step, workers, skip_known)

    duration = time.monotonic() - t0

    # Record scan
    async with db.session() as session:
        await ScanRepo(session).create(
            range_start=lo,
            range_end=hi,
            until_date=until,
            tickets_found=len(found),
            errors=n_errs,
            duration_s=duration,
        )

    console.print()

    if not found:
        console.print(f"no tickets found on or before {target}.")
        return

    found.sort(key=lambda t: t.issue_date)
    console.print(build_ticket_table(found))

    if summary:
        print_summary(found)

    if output:
        with open(output, "w") as f:
            json.dump([t.to_dict() for t in found], f, indent=2)
        console.print(f"[dim]saved {len(found)} tickets to {output}[/]")


