"""backfill details -- fetch missing detail fields for tickets with keys."""

from __future__ import annotations

import time
from typing import Annotated

from cyclopts import Parameter
from cyclopts import validators as cyclopts_validators

from pgh_ticket.core import Database, TicketView, make_progress, resource_map
from pgh_ticket.core.fmt import console
from pgh_ticket.core.utils import batch_flush, resolve_proxy
from pgh_ticket.core.client import ClientPool, PortalClient
from pgh_ticket.repos import TicketRepo


async def _fetch_details(client: PortalClient, row: TicketView) -> dict | None:
    if not row.ticket_key:
        return None
    results = await client.search(row.number)
    if not results:
        return None
    key = next((r.ticket_key for r in results if r.ticket_key), row.ticket_key)
    detail = await client.details(key)
    if detail:
        return {
            "ticket_number": row.number,
            "ticket_key": key,
            "vehicle_make": detail.vehicle_make or row.vehicle_make,
            "license_plate": row.license_plate,
            "state": row.state,
            "issue_date": row.issue_date,
            "location": detail.location or row.location,
            "violation": detail.violation or row.violation,
            "amount_due": row.amount_due,
            "due_date": detail.due_date or row.due_date,
            "officer": detail.officer or row.officer,
            "notes": detail.notes or row.notes,
            "status": row.status,
            "ticket_type": row.ticket_type,
        }
    return None


async def _flush(db: Database, data: list[dict]) -> int:
    async with db.session() as session:
        return await TicketRepo(session).bulk_upsert(data)


async def details(
    workers: Annotated[
        int,
        Parameter(
            ("-j", "--workers"),
            help="max concurrent workers (auto-tuned down if errors spike)",
            validator=cyclopts_validators.Number(gte=1),
        ),
    ] = 5,
    limit: Annotated[
        int | None,
        Parameter(
            ("-n", "--limit"),
            help="max tickets to process (default: all)",
            validator=cyclopts_validators.Number(gte=1),
        ),
    ] = None,
    batch_size: Annotated[
        int,
        Parameter(
            ("-b", "--batch-size"),
            help="flush to db after this many details (default: 500)",
            validator=cyclopts_validators.Number(gte=1),
        ),
    ] = 500,
    chunk_size: Annotated[
        int,
        Parameter(
            ("--chunk-size",),
            help="items per auto-scale chunk (default: 50)",
            validator=cyclopts_validators.Number(gte=1),
        ),
    ] = 50,
    *,
    proxy: list[str] | None = None,
    db: Annotated[Database, Parameter(parse=False)],
) -> None:
    """Fetch detail fields for tickets that have a key but missing location."""

    async with db.session() as session:
        rows = await TicketRepo(session).list_missing_details(limit=limit)

    if not rows:
        console.print("[green]all tickets already have detail fields.[/]")
        return

    total = len(rows)
    t0 = time.monotonic()
    batch: list[dict] = []
    empty: list[str] = []
    failed: list[str] = []

    max_workers = workers
    current_workers = workers

    progress = make_progress()
    task = progress.add_task(
        f"fetching details [{current_workers}w]",
        total=total,
        status="starting...",
    )

    proxies = resolve_proxy(proxy)
    proxy_list: list[str] = []
    if isinstance(proxies, list):
        proxy_list = proxies
    elif isinstance(proxies, str):
        proxy_list = [proxies]

    async with ClientPool(proxy_list, max_workers) as pool:
        with progress:
            views = [row.to_view() for row in rows]

            for i in range(0, len(views), chunk_size):
                chunk = views[i : i + chunk_size]
                clients = [pool.acquire() for _ in range(current_workers)]
                chunk_results, chunk_failed = await resource_map(
                    chunk,
                    clients,
                    _fetch_details,
                    progress=progress,
                    task_id=task,
                )

                # chunk_failed are exceptions; empty are None returns
                for item in chunk:
                    if item in chunk_failed:
                        failed.append(item.number)
                    elif not any(r["ticket_number"] == item.number for r in chunk_results):
                        empty.append(item.number)

                for item in chunk_results:
                    batch.append(item)
                    if len(batch) >= batch_size:
                        await batch_flush(batch, lambda data: _flush(db, data), batch_size)

                # auto-scale for next chunk
                if len(chunk) > 0:
                    success_rate = len(chunk_results) / len(chunk)
                    if success_rate > 0.95 and current_workers < max_workers:
                        current_workers += 1
                        progress.update(task, description=f"fetching details [{current_workers}w]")
                    elif success_rate < 0.70 and current_workers > 1:
                        current_workers -= 1
                        progress.update(task, description=f"fetching details [{current_workers}w]")

            if batch:
                await _flush(db, batch)

    elapsed = time.monotonic() - t0
    rate = total / elapsed if elapsed > 0 else 0.0
    found = len(batch)
    console.print(
        f"\n[bold]{total}/{total}"
        f" — {found} details, {len(empty)} empty, {len(failed)} failed"
        f" ({rate:.1f}/s)[/]"
    )

    if empty:
        console.print(f"[yellow]empty ({len(empty)}):[/] {', '.join(empty[:20])}")
        if len(empty) > 20:
            console.print(f"[dim]... and {len(empty) - 20} more[/]")

    if failed:
        console.print(f"[red]failed ({len(failed)}):[/] {', '.join(failed[:20])}")
        if len(failed) > 20:
            console.print(f"[dim]... and {len(failed) - 20} more[/]")
