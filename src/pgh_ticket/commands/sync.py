"""/sync -- probe for tickets issued on a specific date."""

from __future__ import annotations

import asyncio
import json
import signal
import time
from datetime import UTC, date, datetime
from typing import Annotated

from cyclopts import Parameter
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TaskID, TaskProgressColumn, TextColumn
from rich.table import Table
from sqlalchemy import delete, func

from pgh_ticket.client import Client
from pgh_ticket.commands.base import BaseCommand
from pgh_ticket.commands.common import CommonParams
from cyclopts import validators as cyclopts_validators

from pgh_ticket.db import Database
from pgh_ticket.models import Cluster, ErrorLog, Scan, Ticket
from pgh_ticket.utils import TicketView, parse_date, print_summary
from pgh_ticket import validators as pgh_validators

LO: int = 2_078_060
HI: int = 9_262_307
BACKOFF_LONG: int = 180
BACKOFF_SHORT: int = 30
FRONTIER_STEP: int = 500

console = Console(stderr=True, force_terminal=True)


class SyncCommand(BaseCommand):
    """Probe ticket numbers looking for a specific issue date."""

    @staticmethod
    def _build_table(found: list[TicketView], target: str) -> Table:
        table = Table(title=f"{len(found)} tickets on {target}")
        table.add_column("number", style="cyan", no_wrap=True)
        table.add_column("type")
        table.add_column("plate")
        table.add_column("st", justify="center")
        table.add_column("status")
        table.add_column("amount", justify="right")
        for t in found:
            table.add_row(
                t.number,
                t.ticket_type,
                t.license_plate,
                t.state,
                t.status,
                t.amount_due,
            )
        return table

    async def __call__(
        self,
        date_str: Annotated[str, Parameter(help="target date (YYYY-MM-DD)")],
        *,
        workers: Annotated[
            int,
            Parameter(
                ("-j", "--workers"),
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
        common: CommonParams = CommonParams(),
        db: Annotated[Database, Parameter(parse=False)] = None,  # type: ignore[assignment]
    ) -> None:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()

        async with db.session() as session:
            from sqlalchemy import select
            clusters_result = await session.execute(select(Cluster).order_by(Cluster.range_start))
            clusters = clusters_result.scalars().all()

        adaptive = bool(clusters)

        if adaptive:
            probe_ranges = Cluster.build_probe_ranges(clusters, step, LO, HI, FRONTIER_STEP)
            total_probes = sum(
                max(1, (end - start) // s + 1) for start, end, s in probe_ranges
            )
            console.print(f"adaptive sync: {len(clusters)} clusters + frontier")
            console.print(f"probes: ~{total_probes:,} (vs ~{((HI - LO) // step):,} full-range)")
        else:
            probe_ranges = [(LO, HI, step)]
            console.print("no clusters found — falling back to full range")
            console.print(f"range: {LO:,} to {HI:,} | workers: {workers}")

        if common.proxy:
            console.print(f"proxy: {common.proxy}")
        console.print()

        async with Client(proxy=common.proxy) as cl:
            loop = asyncio.get_event_loop()
            main_task: asyncio.Task | None = None

            def _on_signal() -> None:
                if main_task:
                    main_task.cancel()

            loop.add_signal_handler(signal.SIGTERM, _on_signal)
            loop.add_signal_handler(signal.SIGINT, _on_signal)

            try:
                main_task = asyncio.ensure_future(
                    self._run(
                        cl, db, target, date_str, workers, probe_ranges, adaptive
                    )
                )
                found, n_errs, t0, needs_rebuild = await main_task
            except asyncio.CancelledError:
                console.print("\n[yellow]interrupted — data flushed to db on each find.[/]")
                return

        if needs_rebuild or not adaptive:
            console.print("[dim]rebuilding clusters from ticket data...[/]")
            async with db.session() as session:
                await session.execute(delete(Cluster))
                nums_result = await session.execute(
                    Ticket.__table__.select().order_by(Ticket.ticket_number)
                )
                nums = [int(row.ticket_number) for row in nums_result.scalars().all()]

                if nums:
                    built: list[tuple[int, int]] = []
                    start = end = nums[0]
                    for n in nums[1:]:
                        if n - end <= 100:
                            end = n
                        else:
                            built.append((start, end))
                            start = end = n
                    built.append((start, end))

                    for start, end in built:
                        count_result = await session.execute(
                            Ticket.__table__.select().where(
                                Ticket.ticket_number >= str(start),
                                Ticket.ticket_number <= str(end),
                            )
                        )
                        count = len(count_result.scalars().all())
                        session.add(
                            Cluster(
                                range_start=start,
                                range_end=end,
                                ticket_count=count,
                            )
                        )
                    await session.commit()

        duration = time.monotonic() - t0
        async with db.session() as session:
            await Scan.create(
                session=session,
                range_start=LO,
                range_end=HI,
                until_date=date_str,
                tickets_found=len(found),
                errors=n_errs,
                duration_s=duration,
            )

        console.print()

        if not found:
            console.print(f"no tickets found on {target}.")
            return

        found.sort(key=lambda t: t.issue_date)
        console.print(SyncCommand._build_table(found, date_str))

        if summary:
            print_summary(found)

        if output:
            with open(output, "w") as f:
                json.dump([t.to_dict() for t in found], f, indent=2)
            console.print(f"[dim]saved to {output}[/]")

    @staticmethod
    async def _run(
        cl: Client,
        db: Database,
        target: date,
        date_str: str,
        workers: int,
        probe_ranges: list[tuple[int, int, int]],
        adaptive: bool,
    ) -> tuple[list[TicketView], int, float, bool]:
        lock = asyncio.Lock()
        found: list[TicketView] = []
        seen: set[str] = set()
        w_errs: dict[int, int] = {}
        n_errs = 0
        q: asyncio.Queue[TicketView | None] = asyncio.Queue()
        sem = asyncio.Semaphore(workers)
        sem_enrich = asyncio.Semaphore(workers)
        t0 = time.monotonic()
        needs_rebuild = False

        cluster_ends: set[int] = set()
        if adaptive:
            async with db.session() as session:
                from sqlalchemy import select
                clusters_result = await session.execute(
                    select(Cluster).order_by(Cluster.range_start)
                )
                for c in clusters_result.scalars().all():
                    cluster_ends.add(c.range_end)

        async def fetch(n: int, wid: int) -> list:
            nonlocal n_errs
            try:
                results = await cl.search(str(n))
                w_errs[wid] = 0
                return results
            except Exception as exc:
                async with lock:
                    n_errs += 1
                    w_errs[wid] = w_errs.get(wid, 0) + 1
                async with db.session() as s:
                    await ErrorLog.log(s, number=str(n), command="sync", exc=exc)
                consec = w_errs[wid]
                if consec >= 5 and consec % 5 == 0:
                    console.print(
                        f"\n  [yellow]worker {wid}: {consec} errors, sleeping 3min...[/]"
                    )
                    await asyncio.sleep(BACKOFF_LONG)
                elif consec > 0 and consec % 3 == 0:
                    console.print(
                        f"\n  [yellow]worker {wid}: {consec} errors, sleeping 30s...[/]"
                    )
                    await asyncio.sleep(BACKOFF_SHORT)
                return []

        def check(raw: list, probe_num: int) -> None:
            nonlocal needs_rebuild
            for r in raw:
                tv = r.to_ticket_view()
                if parse_date(tv.issue_date) == target and tv.number not in seen:
                    seen.add(tv.number)
                    found.append(tv)
                    q.put_nowait(tv)
                if adaptive:
                    num = int(tv.number) if tv.number else 0
                    if num and all(num > end for end in cluster_ends):
                        needs_rebuild = True

        async def enrich() -> None:
            while (t := await q.get()) is not None:
                try:
                    async with sem_enrich:
                        raw = [t] if t.ticket_key else await cl.search(t.number)
                        for r in raw:
                            if not r.ticket_key:
                                continue
                            try:
                                details = await cl.details(r.ticket_key)
                            except Exception as exc:
                                async with db.session() as s:
                                    await ErrorLog.log(s, number=r.ticket_key or "", command="sync-detail", exc=exc)
                                continue
                            if details:
                                t.vehicle_make = details.vehicle_make or t.vehicle_make
                                t.location = details.location or t.location
                                t.violation = details.violation or t.violation
                                t.officer = details.officer or t.officer
                                t.due_date = details.due_date or t.due_date
                                t.notes = details.notes or t.notes
                            break

                    async with db.session() as session:
                        await session.merge(Ticket(**t.to_model_dict()))
                        await session.commit()
                except Exception:
                    pass
                finally:
                    q.task_done()

        nums: list[int] = []
        for start, end, s in probe_ranges:
            nums.extend(range(start, end + 1, s))

        async def probe(n: int, wid: int, task: TaskID, progress: Progress) -> None:
            async with sem:
                results = await fetch(n, wid)
            async with lock:
                if results:
                    check(results, n)
                progress.update(
                    task,
                    advance=1,
                    status=f"[green]{len(found)}[/] found • [red]{n_errs}[/] errs",
                )

        async def probe_all(task: TaskID, progress: Progress) -> None:
            await asyncio.gather(
                *[probe(n, i % workers, task, progress) for i, n in enumerate(nums)],
                return_exceptions=True,
            )
            for _ in range(workers):
                await q.put(None)

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TextColumn("{task.fields[status]}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("probing", total=len(nums), status="starting...")
            await asyncio.gather(
                probe_all(task, progress),
                *[enrich() for _ in range(workers)],
            )

        return found, n_errs, t0, needs_rebuild


sync_cmd = SyncCommand()
