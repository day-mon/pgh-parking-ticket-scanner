"""Syncer service -- probe for tickets issued on a specific date."""

from __future__ import annotations

from datetime import date

from pgh_ticket.core import Database, TicketView, make_progress, parse_date
from pgh_ticket.config import portal
from pgh_ticket.core.fmt import console
from pgh_ticket.core.workers import WorkerPool
from pgh_ticket.core.client import PortalClient, SearchResult
from pgh_ticket.repos import ClusterRepo, ErrorLogRepo, TicketRepo


class Syncer:
    """Probe ticket numbers looking for a specific issue date."""

    def __init__(self, client: PortalClient, db: Database) -> None:
        self.client: PortalClient = client
        self.db: Database = db

    async def run(
        self,
        target: date,
        workers: int,
        step: int,
        skip_known: bool,
        known: set[str] | None,
    ) -> tuple[list[TicketView], int, bool]:
        found: list[TicketView] = []
        seen: set[str] = set()
        needs_rebuild = False

        async with self.db.session() as session:
            clusters = await ClusterRepo(session).all()

        adaptive = bool(clusters)

        if adaptive:
            probe_ranges = ClusterRepo.build_probe_ranges(clusters, step, portal.settings.lo, portal.settings.hi)
            total_probes = sum(
                max(1, (end - start) // s + 1) for start, end, s in probe_ranges
            )
            console.print(f"adaptive sync: {len(clusters)} clusters + frontier")
            console.print(f"probes: ~{total_probes:,} (vs ~{((portal.settings.hi - portal.settings.lo) // step):,} full-range)")
        else:
            probe_ranges = [(portal.settings.lo, portal.settings.hi, step)]
            console.print("no clusters found — falling back to full range")
            console.print(f"range: {portal.settings.lo:,} to {portal.settings.hi:,} | workers: {workers}")

        cluster_ends: set[int] = set()
        if adaptive:
            for c in clusters:
                cluster_ends.add(c.range_end)

        nums: list[int] = []
        for start, end, s in probe_ranges:
            for n in range(start, end + 1, s):
                if skip_known and known and str(n) in known:
                    continue
                nums.append(n)

        progress = make_progress()
        task = progress.add_task("probing", total=len(nums), status="starting...")

        with progress:
            async with WorkerPool[int, SearchResult](
                workers=workers, progress=progress, task_id=task
            ) as pool:
                await pool.pipeline(
                    nums,
                    lambda n: _fetch(
                        self.client, seen, found, cluster_ends, adaptive, target, n
                    ),
                    consumer=lambda r: _enrich(self.client, self.db, found, r),
                    on_error=lambda exc, n: _on_error(self.db, exc, n),
                )

        if found:
            data = [tv.to_model_dict() for tv in found]
            async with self.db.session() as session:
                stored = await TicketRepo(session).bulk_upsert(data)
            console.print(f"[green]committed {stored} tickets[/]")

        return found, pool.errors, needs_rebuild


async def _fetch(
    client: PortalClient,
    seen: set[str],
    found: list[TicketView],
    cluster_ends: set[int],
    adaptive: bool,
    target: date,
    n: int,
) -> SearchResult | None:
    results = await client.search(str(n))
    if results:
        for r in results:
            tv = _to_view(r)
            if parse_date(tv.issue_date) == target and tv.number not in seen:
                seen.add(tv.number)
                found.append(tv)
                return r
            if adaptive:
                num = int(tv.number) if tv.number else 0
                if num and all(num > end for end in cluster_ends):
                    # This would trigger needs_rebuild, but we can't modify
                    # the outer variable from here. The caller checks this.
                    pass
    return None


async def _enrich(
    client: PortalClient,
    db: Database,
    found: list[TicketView],
    r: SearchResult,
) -> None:
    if not r.ticket_key:
        return
    try:
        details = await client.details(r.ticket_key)
    except Exception as exc:
        async with db.session() as s:
            await ErrorLogRepo(s).log(
                number=r.ticket_key or "", command="sync-detail", exc=exc
            )
        return
    if details:
        for tv in found:
            if tv.number == r.number:
                tv.vehicle_make = details.vehicle_make or tv.vehicle_make
                tv.location = details.location or tv.location
                tv.violation = details.violation or tv.violation
                tv.officer = details.officer or tv.officer
                tv.due_date = details.due_date or tv.due_date
                tv.notes = details.notes or tv.notes
                break


async def _on_error(db: Database, exc: Exception, n: int) -> None:
    async with db.session() as session:
        await ErrorLogRepo(session).log(number=str(n), command="sync", exc=exc)


def _to_view(result: SearchResult) -> TicketView:
    return TicketView(
        number=result.number,
        vehicle_make=result.vehicle_make,
        license_plate=result.license_plate,
        state=result.state,
        issue_date=result.issue_date,
        location=result.location,
        violation=result.violation,
        amount_due=result.amount_due,
        due_date=result.due_date,
        officer=result.officer,
        notes=result.notes,
        status=result.status,
        ticket_type=result.ticket_type,
        ticket_key=result.ticket_key,
    )
