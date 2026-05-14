"""/scan -- two-phase ticket collection over a number range."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import UTC, date, datetime
from typing import Annotated

from cyclopts import Parameter
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from pgh_ticket.client import Client
from pgh_ticket.commands.base import BaseCommand
from pgh_ticket.commands.common import CommonParams
from cyclopts import validators as cyclopts_validators

from pgh_ticket.db import Database
from pgh_ticket.models import Cluster, ErrorLog, Scan, Ticket
from pgh_ticket.utils import TicketView, parse_date, print_summary
from pgh_ticket import validators as pgh_validators

console = Console(stderr=True, force_terminal=True)


def _status(found: int, stored: int, errs: int) -> str:
    return f"[green]{found}[/] in range • [dim]{stored}[/] stored • [red]{errs}[/] errs"


class ScanCommand(BaseCommand):
    """Two-phase scan: probe for clusters, then deep-scan windows."""

    @staticmethod
    def _merge_hit_windows(hits: list[int], lo: int, hi: int, step: int) -> list[tuple[int, int]]:
        raw_windows = [(max(lo, h - step // 2), min(hi, h + step // 2)) for h in sorted(hits)]
        raw_windows.sort()
        merged: list[tuple[int, int]] = []
        for a, b in raw_windows:
            if merged and a <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        return merged

    @staticmethod
    def _build_table(found: list[TicketView]) -> Table:
        dates = {d for t in found if (d := parse_date(t.issue_date)) is not None}
        table = Table(title=f"{len(found)} tickets from {min(dates)} to {max(dates)}")
        table.add_column("number", style="cyan", no_wrap=True)
        table.add_column("date", style="magenta")
        table.add_column("type")
        table.add_column("plate")
        table.add_column("st", justify="center")
        table.add_column("status")
        table.add_column("amount", justify="right")
        for t in found:
            table.add_row(
                t.number,
                t.issue_date,
                t.ticket_type,
                t.license_plate,
                t.state,
                t.status,
                t.amount_due,
            )
        return table

    @staticmethod
    async def _run_probe(
        cl: Client,
        db: Database,
        sem: asyncio.Semaphore,
        lock: asyncio.Lock,
        coarse: list[int],
        errs: list[int],
        hits: list[int],
    ) -> None:
        total = len(coarse)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TextColumn("{task.fields[status]}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("phase 1: probing", total=total, status="starting...")

            async def probe(n: int) -> None:
                async with sem:
                    try:
                        results = await cl.search(str(n))
                    except Exception as exc:
                        async with lock:
                            errs[0] += 1
                        async with db.session() as s:
                            await ErrorLog.log(s, number=str(n), command="scan", exc=exc)
                        results = []
                async with lock:
                    if results:
                        hits.append(n)
                    hits_s = f"[yellow]{len(hits)}[/] hits • [red]{errs[0]}[/] errs"
                    progress.update(task, advance=1, status=hits_s)

            await asyncio.gather(*[probe(n) for n in coarse], return_exceptions=True)

    @staticmethod
    async def _run_deep(
        cl: Client,
        db: Database,
        sem: asyncio.Semaphore,
        lock: asyncio.Lock,
        deep_nums: list[int],
        target: date,
        errs: list[int],
        found: list[TicketView],
        seen: set[str],
    ) -> None:
        total = len(deep_nums)
        stored = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("•"),
            TextColumn("{task.fields[status]}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("phase 2: deep scan", total=total, status="starting...")

            async def deep_work(n: int) -> None:
                nonlocal stored
                async with sem:
                    try:
                        raw = await cl.search(str(n))
                    except Exception as exc:
                        async with lock:
                            errs[0] += 1
                            progress.update(task, advance=1)
                        async with db.session() as s:
                            await ErrorLog.log(s, number=str(n), command="scan-deep", exc=exc)
                        return

                if not raw:
                    async with lock:
                        progress.update(task, advance=1)
                    return

                for r in raw:
                    if not r.ticket_key:
                        continue
                    try:
                        details = await cl.details(r.ticket_key)
                        if details:
                            r = r.merge(details)
                    except Exception as exc:
                        async with lock:
                            errs[0] += 1
                        async with db.session() as s:
                            await ErrorLog.log(s, number=r.ticket_key or "", command="scan-detail", exc=exc)

                async with db.session() as session:
                    for r in raw:
                        tv = r.to_ticket_view()
                        await session.merge(Ticket(**tv.to_model_dict()))
                    await session.commit()

                async with lock:
                    for r in raw:
                        tv = r.to_ticket_view()
                        stored += 1
                        d = parse_date(tv.issue_date)
                        if d and d <= target and tv.number not in seen:
                            seen.add(tv.number)
                            found.append(tv)
                    progress.update(task, advance=1, status=_status(len(found), stored, errs[0]))

            await asyncio.gather(*[deep_work(n) for n in deep_nums], return_exceptions=True)

    async def __call__(
        self,
        number_range: Annotated[
            str,
            Parameter(help="ticket number range (e.g. 8950000-9245300)", validator=pgh_validators.number_range),
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
        common: CommonParams = CommonParams(),
        db: Annotated[Database, Parameter(parse=False)] = None,  # type: ignore[assignment]
    ) -> None:
        target = datetime.strptime(until, "%Y-%m-%d").date()
        lo, hi = (int(x) for x in number_range.split("-"))

        console.print(f"range: {lo:,} to {hi:,} ({(hi - lo + 1):,} numbers)")
        console.print(f"until: {target} | step: {step} | workers: {workers}")
        if common.proxy:
            console.print(f"proxy: {common.proxy}")
        console.print()

        errs = [0]
        hits: list[int] = []
        found: list[TicketView] = []
        seen: set[str] = set()
        t0 = time.monotonic()

        sem = asyncio.Semaphore(workers)
        lock = asyncio.Lock()

        async with Client(proxy=common.proxy) as cl:
            coarse = list(range(lo, hi + 1, step))
            await ScanCommand._run_probe(cl, db, sem, lock, coarse, errs, hits)

            if not hits:
                console.print("no hits in range.")
                return

            console.print(f"\nfound [yellow]{len(hits)}[/] clusters, deep-scanning...")

            merged = ScanCommand._merge_hit_windows(hits, lo, hi, step)
            deep_nums: list[int] = []
            for a, b in merged:
                deep_nums.extend(range(a, b + 1))

            await ScanCommand._run_deep(cl, db, sem, lock, deep_nums, target, errs, found, seen)

        duration = time.monotonic() - t0

        # Record scan in db
        async with db.session() as session:
            await Scan.create(
                session=session,
                range_start=lo,
                range_end=hi,
                until_date=until,
                tickets_found=len(found),
                errors=errs[0],
                duration_s=duration,
            )

            # Rebuild clusters
            from sqlalchemy import delete

            await session.execute(delete(Cluster))
            await Cluster.rebuild_from_tickets(session, gap=100)

        console.print()

        if not found:
            console.print(f"no tickets found on or before {target}.")
            return

        found.sort(key=lambda t: t.issue_date)
        console.print(self._build_table(found))

        if summary:
            print_summary(found)

        if output:
            with open(output, "w") as f:
                json.dump([t.to_dict() for t in found], f, indent=2)
            console.print(f"[dim]saved {len(found)} tickets to {output}[/]")


scan_cmd = ScanCommand()
