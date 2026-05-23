"""Scanner service -- two-phase ticket collection."""

from __future__ import annotations

from datetime import date

from pgh_ticket.core import Database, TicketView, make_progress, parse_date
from pgh_ticket.core.client import PortalClient, SearchResult
from pgh_ticket.core.fmt import console
from pgh_ticket.core.workers import WorkerPool
from pgh_ticket.repos import ClusterRepo, ErrorLogRepo, TicketRepo


class Scanner:
    """Two-phase scan: probe for clusters, then deep-scan windows."""

    def __init__(self, client: PortalClient, db: Database) -> None:
        self.client: PortalClient = client
        self.db: Database = db

    @staticmethod
    def merge_hit_windows(hits: list[int], lo: int, hi: int, step: int) -> list[tuple[int, int]]:
        raw_windows = [(max(lo, h - step // 2), min(hi, h + step // 2)) for h in sorted(hits)]
        raw_windows.sort()
        merged: list[tuple[int, int]] = []
        for a, b in raw_windows:
            if merged and a <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        return merged

    async def probe(
        self,
        coarse: list[int],
        workers: int,
        known: set[int],
    ) -> list[int]:
        progress = make_progress()
        task = progress.add_task("phase 1: probing", total=len(coarse), status="starting...")

        with progress:
            async with WorkerPool[int, int | None](
                workers=workers, progress=progress, task_id=task
            ) as pool:
                hits = await pool.map(
                    coarse,
                    lambda n: _probe_one(self.client, known, n),
                    on_error=lambda exc, n: _probe_on_error(self.db, exc, n),
                )

        return [h for h in hits if h is not None]

    async def deep_scan(
        self,
        deep_nums: list[int],
        target: date,
        workers: int,
    ) -> tuple[list[TicketView], int]:
        found: list[TicketView] = []
        seen: set[str] = set()

        progress = make_progress()
        task = progress.add_task("phase 2: deep scan", total=len(deep_nums), status="starting...")

        with progress:
            async with WorkerPool[int, list[TicketView] | None](
                workers=workers, progress=progress, task_id=task
            ) as pool:
                batch_results = await pool.map(
                    deep_nums,
                    lambda n: _deep_one(self.client, self.db, seen, target, n),
                    on_error=lambda exc, n: _deep_on_error(self.db, exc, n),
                )
                for batch in batch_results:
                    if batch:
                        found.extend(batch)

        return found, pool.errors

    async def run(
        self,
        lo: int,
        hi: int,
        target: date,
        step: int,
        workers: int,
        skip_known: bool,
    ) -> tuple[list[TicketView], int]:
        known: set[int] = set()
        if skip_known:
            async with self.db.session() as session:
                known = await TicketRepo(session).get_numbers_in_range(lo, hi)
            console.print(f"[dim]found {len(known):,} known tickets in range[/]")

        coarse = list(range(lo, hi + 1, step))
        hits = await self.probe(coarse, workers, known)

        if not hits:
            return [], 0

        console.print(f"\nfound [yellow]{len(hits)}[/] clusters, deep-scanning...")

        merged = self.merge_hit_windows(hits, lo, hi, step)
        deep_nums: list[int] = []
        for a, b in merged:
            for n in range(a, b + 1):
                if n not in known:
                    deep_nums.append(n)

        if not deep_nums:
            console.print("[dim]all numbers already known, nothing to deep-scan[/]")
            return [], 0

        console.print(f"[dim]deep-scanning {len(deep_nums):,} unknown numbers[/]")
        found, n_errs = await self.deep_scan(deep_nums, target, workers)

        async with self.db.session() as session:
            await ClusterRepo(session).clear()
            await ClusterRepo(session).rebuild(gap=100)

        return found, n_errs


async def _probe_one(client: PortalClient, known: set[int], n: int) -> int | None:
    if n in known:
        return n
    results = await client.search(str(n))
    return n if results else None


async def _probe_on_error(db: Database, exc: Exception, n: int) -> None:
    async with db.session() as session:
        await ErrorLogRepo(session).log(number=str(n), command="scan", exc=exc)


async def _deep_one(
    client: PortalClient,
    db: Database,
    seen: set[str],
    target: date,
    n: int,
) -> list[TicketView] | None:
    raw = await client.search(str(n))
    if not raw:
        return None

    for r in raw:
        if not r.ticket_key:
            continue
        try:
            details = await client.details(r.ticket_key)
            if details:
                r = _merge_detail(r, details)
        except Exception as exc:
            async with db.session() as session:
                await ErrorLogRepo(session).log(
                    number=r.ticket_key or "", command="scan-detail", exc=exc
                )

    if raw:
        async with db.session() as session:
            data = [_to_model_dict(r) for r in raw]
            await TicketRepo(session).bulk_upsert(data)

    results: list[TicketView] = []
    for r in raw:
        tv = _to_view(r)
        d = parse_date(tv.issue_date)
        if d and d <= target and tv.number not in seen:
            seen.add(tv.number)
            results.append(tv)
    return results


async def _deep_on_error(db: Database, exc: Exception, n: int) -> None:
    async with db.session() as session:
        await ErrorLogRepo(session).log(number=str(n), command="scan-deep", exc=exc)


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


def _to_model_dict(result: SearchResult) -> dict[str, object]:
    return {
        "ticket_number": result.number,
        "ticket_key": result.ticket_key,
        "vehicle_make": result.vehicle_make,
        "license_plate": result.license_plate,
        "state": result.state,
        "issue_date": result.issue_date,
        "location": result.location,
        "violation": result.violation,
        "amount_due": result.amount_due,
        "due_date": result.due_date,
        "officer": result.officer,
        "notes": result.notes,
        "status": result.status,
        "ticket_type": result.ticket_type,
    }


def _merge_detail(result: SearchResult, detail) -> SearchResult:

    return SearchResult(
        number=result.number,
        ticket_type=result.ticket_type,
        license_plate=result.license_plate,
        state=result.state,
        issue_date=result.issue_date,
        status=result.status,
        amount_due=result.amount_due,
        ticket_key=result.ticket_key,
        vehicle_make=detail.vehicle_make or result.vehicle_make,
        location=detail.location or result.location,
        violation=detail.violation or result.violation,
        due_date=detail.due_date or result.due_date,
        officer=detail.officer or result.officer,
        notes=detail.notes or result.notes,
    )
